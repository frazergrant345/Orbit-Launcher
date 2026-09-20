"""The main search popup window."""
import math
from typing import Optional

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gio, GLib, Gtk, Pango

try:
    gi.require_version("GtkLayerShell", "0.1")
    from gi.repository import GtkLayerShell
except (ImportError, ValueError):
    GtkLayerShell = None

from . import backend
from .config import load_config
from .settings import SettingsWindow
from .usage import UsageStore


def _rounded_rect_path(cr, x, y, width, height, radius):
    """Trace a rounded-rectangle path on a Cairo context (does not fill/stroke)."""
    radius = max(0, min(radius, width / 2, height / 2))
    cr.new_sub_path()
    cr.arc(x + width - radius, y + radius, radius, -math.pi / 2, 0)
    cr.arc(x + width - radius, y + height - radius, radius, 0, math.pi / 2)
    cr.arc(x + radius, y + height - radius, radius, math.pi / 2, math.pi)
    cr.arc(x + radius, y + radius, radius, math.pi, 3 * math.pi / 2)
    cr.close_path()


class ResultRow(Gtk.ListBoxRow):
    def __init__(self, result: backend.Result, icon_size: int):
        super().__init__()
        self.result = result
        self.get_style_context().add_class("launcher-result-row")

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        box.set_margin_top(4)
        box.set_margin_bottom(4)

        image = Gtk.Image.new_from_gicon(
            _icon_for_name(result.icon_name), Gtk.IconSize.DND
        )
        image.set_pixel_size(icon_size)
        box.pack_start(image, False, False, 0)

        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        title = Gtk.Label(label=result.title, xalign=0)
        title.get_style_context().add_class("launcher-result-title")
        title.set_ellipsize(Pango.EllipsizeMode.END)
        text_box.pack_start(title, False, False, 0)

        if result.subtitle:
            subtitle = Gtk.Label(label=result.subtitle, xalign=0)
            subtitle.get_style_context().add_class("launcher-result-subtitle")
            subtitle.set_ellipsize(Pango.EllipsizeMode.END)
            text_box.pack_start(subtitle, False, False, 0)

        box.pack_start(text_box, True, True, 0)

        badge = Gtk.Label(label=result.kind)
        badge.get_style_context().add_class("launcher-badge")
        badge.get_style_context().add_class(f"launcher-badge-{result.kind.lower()}")
        badge.set_valign(Gtk.Align.CENTER)
        box.pack_end(badge, False, False, 0)

        self.add(box)


def _icon_for_name(icon_name: str) -> Gio.Icon:
    try:
        if "/" in icon_name:
            return Gio.FileIcon.new(Gio.File.new_for_path(icon_name))
        return Gio.ThemedIcon.new_with_default_fallbacks(icon_name)
    except GLib.Error:
        return Gio.ThemedIcon.new("application-x-executable")


# GNOME's named accent palette (org.gnome.desktop.interface accent-color).
_GNOME_ACCENT_COLORS = {
    "blue": "#3584e4", "teal": "#2190a4", "green": "#3a944a",
    "yellow": "#c88800", "orange": "#ed5b00", "red": "#e62d42",
    "pink": "#d56199", "purple": "#9141ac", "slate": "#6f8396",
}


def _get_gnome_accent_color() -> Optional[str]:
    """Best-effort read of GNOME's system accent color, if the schema/key
    exists (GNOME 42+ desktop interface accent-color setting)."""
    try:
        source = Gio.SettingsSchemaSource.get_default()
        if source is None or source.lookup("org.gnome.desktop.interface", True) is None:
            return None
        settings = Gio.Settings.new("org.gnome.desktop.interface")
        if "accent-color" not in settings.list_keys():
            return None
        name = settings.get_string("accent-color")
        return _GNOME_ACCENT_COLORS.get(name)
    except GLib.Error:
        return None


def _apply_blur_hint(window: Gtk.Window, enabled: bool) -> None:
    """Best-effort request for compositor-side background blur.

    True background blur isn't part of GTK3 itself and depends entirely on
    the desktop compositor. This sets the `_KDE_NET_WM_BLUR_BEHIND_REGION`
    hint via GDK's portable property API, which KWin (X11) honours natively;
    on other compositors (e.g. GNOME/Mutter on Wayland) this silently has no
    effect on its own — pair it with transparency and, on GNOME, the "Blur my
    Shell" extension for a similar look.
    """
    gdk_window = window.get_window()
    if gdk_window is None:
        return
    try:
        atom = Gdk.Atom.intern("_KDE_NET_WM_BLUR_BEHIND_REGION", False)
        cardinal = Gdk.Atom.intern("CARDINAL", False)
        if enabled:
            gdk_window.property_change(atom, cardinal, 32, Gdk.PropMode.REPLACE, b"")
        else:
            gdk_window.property_delete(atom)
    except (GLib.Error, TypeError):
        # Blur is a cosmetic best-effort feature; never let it break the app.
        pass


class LauncherWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app)
        self.config = load_config()
        self.app_provider = backend.AppProvider()
        self.settings_provider = backend.SettingsProvider()
        self.recent_files_provider = backend.RecentFilesProvider()
        self.software_provider = backend.SoftwareCenterProvider()
        self.snippet_provider = backend.SnippetProvider(self.config.get("snippets", []))
        self.clipboard_history = backend.ClipboardHistory()
        self.usage = UsageStore()
        self._settings_window = None
        self._clipboard_signal_id = None

        self.set_name("launcher-popup")
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_type_hint(Gdk.WindowTypeHint.DIALOG)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_default_size(self.config["window_width"], -1)

        self._layer_shell_positioned = False
        display = Gdk.Display.get_default()
        is_wayland = display is not None and display.get_name().startswith("wayland")
        if GtkLayerShell is not None and is_wayland and GtkLayerShell.is_supported():
            GtkLayerShell.init_for_window(self)
            GtkLayerShell.set_layer(self, GtkLayerShell.Layer.OVERLAY)
            GtkLayerShell.set_keyboard_mode(self, GtkLayerShell.KeyboardMode.ON_DEMAND)
            self._layer_shell_positioned = True
            self._configure_layer_shell_position()

        screen = Gdk.Screen.get_default()
        if screen is not None:
            visual = screen.get_rgba_visual()
            if visual is not None:
                self.set_visual(visual)

        self.connect("key-press-event", self._on_key_press)
        self.connect("focus-out-event", self._on_focus_out)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(root)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        header.get_style_context().add_class("launcher-header")
        root.pack_start(header, False, False, 0)

        self.entry = Gtk.Entry()
        self.entry.set_has_frame(False)
        self.entry.set_placeholder_text("Search apps, or type a calculation…")
        self.entry.set_icon_from_icon_name(
            Gtk.EntryIconPosition.PRIMARY, "system-search-symbolic"
        )
        self.entry.get_style_context().add_class("launcher-entry")
        self.entry.connect("changed", self._on_search_changed)
        self.entry.connect("activate", self._on_activate)
        header.pack_start(self.entry, True, True, 0)

        settings_button = Gtk.Button()
        settings_button.set_relief(Gtk.ReliefStyle.NONE)
        settings_button.set_image(
            Gtk.Image.new_from_icon_name("emblem-system-symbolic", Gtk.IconSize.BUTTON)
        )
        settings_button.set_tooltip_text("Settings")
        settings_button.connect("clicked", self._on_settings_clicked)
        settings_button.get_style_context().add_class("launcher-settings-button")
        header.pack_end(settings_button, False, False, 8)

        self.separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        self.separator.get_style_context().add_class("launcher-separator")
        root.pack_start(self.separator, False, False, 0)

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        body.get_style_context().add_class("launcher-body")
        root.pack_start(body, True, True, 0)

        self.empty_state = Gtk.Label(
            label="Type to search apps, run a calculation, or search the web"
        )
        self.empty_state.get_style_context().add_class("launcher-empty-state")
        self.empty_state.set_line_wrap(True)
        body.pack_start(self.empty_state, False, False, 0)

        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_max_content_height(380)
        scroller.set_propagate_natural_height(True)
        self.results_scroller = scroller
        body.pack_start(scroller, True, True, 0)

        self.listbox = Gtk.ListBox()
        self.listbox.get_style_context().add_class("launcher-results")
        self.listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.listbox.connect("row-activated", self._on_row_activated)
        scroller.add(self.listbox)

        self.hint_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        self.hint_bar.get_style_context().add_class("launcher-hint-bar")
        hints = [
            ("\u21b5", "Open"),
            ("Esc", "Close"),
            ("\u2191\u2193", "Navigate"),
        ]
        for key, label in hints:
            hint_label = Gtk.Label(label=f"{key} {label}")
            hint_label.get_style_context().add_class("launcher-hint")
            self.hint_bar.pack_start(hint_label, False, False, 0)
        root.pack_start(self.hint_bar, False, False, 0)

        self._setup_clipboard_monitor()
        self.apply_appearance()
        self.show_all()
        self.hide()
        self.connect("destroy", self._on_destroy)

    def do_draw(self, cr):
        """Hard-clip everything to a rounded rect so no child widget's own
        opaque background can spill past the window's rounded corners."""
        radius = int(self.config.get("corner_radius", 18))
        if radius > 0:
            width = self.get_allocated_width()
            height = self.get_allocated_height()
            _rounded_rect_path(cr, 0, 0, width, height, radius)
            cr.clip()
        Gtk.ApplicationWindow.do_draw(self, cr)

    # -- behaviour -------------------------------------------------

    def present_and_focus(self):
        self.refresh_apps()
        self.entry.set_text("")
        self._update_results([])
        self.show_all()

        if self.config.get("animate_open", True):
            self.set_opacity(0.0)
            self.present()
            self._position_window()
            self._animate_fade_in()
        else:
            self.present()
            self._position_window()

        self.entry.grab_focus()

    def _animate_fade_in(self):
        target_opacity = (
            float(self.config.get("opacity", 0.95))
            if self.config.get("transparency_enabled")
            else 1.0
        )
        steps = 8
        state = {"step": 0}

        def _tick():
            state["step"] += 1
            fraction = state["step"] / steps
            self.set_opacity(target_opacity * fraction)
            return state["step"] < steps

        GLib.timeout_add(12, _tick)

    def refresh_apps(self):
        self.app_provider.refresh()

    def _setup_clipboard_monitor(self):
        if not self.config.get("clipboard_history_enabled", False):
            return
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        self._clipboard_signal_id = clipboard.connect("owner-change", self._on_clipboard_owner_change)

    def _on_clipboard_owner_change(self, clipboard, _event):
        def _receive(_clipboard, text):
            if text:
                self.clipboard_history.add(text)

        clipboard.request_text(_receive)

    def _on_destroy(self, _widget):
        if self._clipboard_signal_id is not None:
            Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).disconnect(self._clipboard_signal_id)
            self._clipboard_signal_id = None

    def apply_appearance(self):
        """(Re-)apply theme mode, transparency and blur from self.config."""
        mode = self.config.get("theme_mode", "system")
        gtk_settings = Gtk.Settings.get_default()
        if gtk_settings is not None and mode != "system":
            gtk_settings.set_property("gtk-application-prefer-dark-theme", mode == "dark")

        if self.config.get("transparency_enabled"):
            opacity = float(self.config.get("opacity", 0.95))
        else:
            opacity = 1.0
        self.set_opacity(opacity)

        _apply_blur_hint(self, self.config.get("blur_enabled", False))
        self._apply_corner_radius()
        self._apply_density_and_accent()

    def _apply_density_and_accent(self):
        density = self.config.get("row_density", "comfortable")
        row_padding = "4px 10px" if density == "compact" else "8px 10px"

        accent_css = ""
        if self.config.get("accent_color_sync", True):
            accent_hex = _get_gnome_accent_color()
            if accent_hex:
                accent_css = (
                    "#launcher-popup .launcher-result-row:selected, "
                    "#launcher-popup .launcher-result-row.selected "
                    f"{{ background-color: {accent_hex}; }} "
                    f"#launcher-popup .launcher-entry {{ caret-color: {accent_hex}; }}"
                )

        css = f"#launcher-popup .launcher-result-row {{ padding: {row_padding}; }} {accent_css}".encode()
        provider = Gtk.CssProvider()
        provider.load_from_data(css)
        screen = Gdk.Screen.get_default()
        if screen is not None:
            Gtk.StyleContext.add_provider_for_screen(
                screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1
            )
        self._density_accent_provider = provider

    def _apply_corner_radius(self):
        radius = int(self.config.get("corner_radius", 18))
        css = (
            f"#launcher-popup {{ border-radius: {radius}px; }} "
            f"#launcher-popup decoration {{ border-radius: {radius}px; }}"
        ).encode()
        provider = Gtk.CssProvider()
        provider.load_from_data(css)
        screen = Gdk.Screen.get_default()
        if screen is not None:
            Gtk.StyleContext.add_provider_for_screen(
                screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1
            )
        self._corner_radius_provider = provider

    def _on_settings_clicked(self, _button):
        if self._settings_window is not None:
            self._settings_window.present()
            return
        self._settings_window = SettingsWindow(self, self._on_settings_saved)
        self._settings_window.connect("destroy", self._on_settings_closed)

    def _on_settings_closed(self, _window):
        self._settings_window = None

    def _on_settings_saved(self, new_config: dict):
        self.config = new_config
        # Defer until after the settings dialog finishes closing itself;
        # some settings (e.g. transparency) need a fresh window to take
        # effect, since a widget's visual can't change once realized.
        GLib.idle_add(self._restart_after_settings)

    def _restart_after_settings(self):
        self.get_application().restart_window()
        return False

    def _position_window(self):
        if self._layer_shell_positioned:
            self._configure_layer_shell_position()
            return

        position = self.config.get("window_position", "top")
        if position == "center":
            self.set_position(Gtk.WindowPosition.CENTER)
            return

        display = Gdk.Display.get_default()
        monitor = display.get_primary_monitor() or display.get_monitor(0)
        if monitor is None:
            self.set_position(Gtk.WindowPosition.CENTER)
            return

        geometry = monitor.get_geometry()
        width, height = self.get_size()
        margin = 60

        if position == "top":
            x = geometry.x + (geometry.width - width) // 2
            y = geometry.y + margin
        elif position == "top-left":
            x = geometry.x + margin
            y = geometry.y + margin
        elif position == "top-right":
            x = geometry.x + geometry.width - width - margin
            y = geometry.y + margin
        else:
            self.set_position(Gtk.WindowPosition.CENTER)
            return

        self.set_position(Gtk.WindowPosition.NONE)
        self.move(x, y)

    def _configure_layer_shell_position(self):
        position = self.config.get("window_position", "top")
        for edge in (GtkLayerShell.Edge.TOP, GtkLayerShell.Edge.BOTTOM,
                     GtkLayerShell.Edge.LEFT, GtkLayerShell.Edge.RIGHT):
            GtkLayerShell.set_anchor(self, edge, False)

        margin = 60
        if position == "top":
            GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.TOP, True)
            GtkLayerShell.set_margin(self, GtkLayerShell.Edge.TOP, margin)
        elif position == "top-left":
            GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.TOP, True)
            GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.LEFT, True)
            GtkLayerShell.set_margin(self, GtkLayerShell.Edge.TOP, margin)
            GtkLayerShell.set_margin(self, GtkLayerShell.Edge.LEFT, margin)
        elif position == "top-right":
            GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.TOP, True)
            GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.RIGHT, True)
            GtkLayerShell.set_margin(self, GtkLayerShell.Edge.TOP, margin)
            GtkLayerShell.set_margin(self, GtkLayerShell.Edge.RIGHT, margin)

    def _on_search_changed(self, entry: Gtk.Entry):
        query = entry.get_text()
        results = []

        shell_result = backend.build_shell_command_result(query)
        if shell_result is not None:
            self._update_results([shell_result])
            return

        snippet_results = self.snippet_provider.search(query)
        if snippet_results:
            self._update_results(snippet_results)
            return

        calc = backend.try_calculate(query)
        if calc is None:
            convert_result = backend.try_convert(query)
            if convert_result is not None:
                results.append(
                    backend.Result(
                        title=convert_result,
                        subtitle=f"{query} = {convert_result}",
                        icon_name="accessories-calculator",
                        action=lambda: self._copy_to_clipboard(convert_result),
                        score=1000,
                        kind="Calc",
                    )
                )
        else:
            results.append(
                backend.Result(
                    title=calc,
                    subtitle=f"{query} = {calc}",
                    icon_name="accessories-calculator",
                    action=lambda: self._copy_to_clipboard(calc),
                    score=1000,
                    kind="Calc",
                )
            )

        ranked = self.app_provider.search(query, self.config["max_results"])
        ranked.extend(self.settings_provider.search(query, limit=4))
        if self.config.get("recent_files_enabled", True):
            try:
                ranked.extend(self.recent_files_provider.search(query, limit=4))
            except (AttributeError, GLib.Error):
                pass
        if self.config.get("clipboard_history_enabled", False):
            ranked.extend(self.clipboard_history.search(query, limit=4))

        for result in ranked:
            result.score += self.usage.boost(result.result_id)
        ranked.sort(key=lambda r: r.score, reverse=True)
        results.extend(ranked[: self.config["max_results"]])

        if (
            query.strip()
            and not any(r.kind == "App" for r in ranked)
            and self.config.get("software_install_enabled", True)
        ):
            software_result = self.software_provider.build_result(query)
            if software_result is not None:
                results.append(software_result)

        if query.strip() and self.config.get("web_search_enabled", True):
            web_result = backend.build_web_search_result(
                query, self.config.get("web_search_engine", "duckduckgo")
            )
            if web_result is not None:
                results.append(web_result)

        self._update_results(results)

    def _update_results(self, results):
        for child in self.listbox.get_children():
            self.listbox.remove(child)

        for result in results:
            row = ResultRow(result, self.config["icon_size"])
            self.listbox.add(row)

        self.empty_state.set_visible(not results)
        self.results_scroller.set_visible(bool(results))
        self.listbox.show_all()
        first = self.listbox.get_row_at_index(0)
        if first:
            self.listbox.select_row(first)

        has_results = bool(results)
        self.empty_state.set_visible(not has_results)
        self.results_scroller.set_visible(has_results)

    def _on_activate(self, entry: Gtk.Entry):
        row = self.listbox.get_selected_row()
        if row is not None:
            self._run_result(row.result)

    def _on_row_activated(self, listbox, row):
        self._run_result(row.result)

    def _run_result(self, result: backend.Result):
        try:
            result.action()
            if result.result_id:
                self.usage.record(result.result_id)
        finally:
            self.hide()

    def _copy_to_clipboard(self, text: str):
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text(text, -1)
        clipboard.store()

    def _on_key_press(self, widget, event):
        if event.keyval == Gdk.KEY_Escape:
            self.hide()
            return True
        if event.keyval in (Gdk.KEY_Down, Gdk.KEY_Up):
            self._move_selection(1 if event.keyval == Gdk.KEY_Down else -1)
            return True
        return False

    def _move_selection(self, direction: int):
        row = self.listbox.get_selected_row()
        index = row.get_index() if row else -1
        new_index = index + direction
        new_row = self.listbox.get_row_at_index(new_index)
        if new_row:
            self.listbox.select_row(new_row)
            new_row.grab_focus()

    def _on_focus_out(self, widget, event):
        if self._settings_window is not None:
            return False
        self.hide()
        return False
