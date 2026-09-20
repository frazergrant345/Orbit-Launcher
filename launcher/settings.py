"""Settings window: appearance (theme, transparency, blur, position) and
web search behaviour. Opened from the cog button in the main search window."""
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, Gtk

from . import __version__
from .config import DEFAULTS, load_config, save_config

try:
    gi.require_version("GtkLayerShell", "0.1")
    from gi.repository import GtkLayerShell
except (ImportError, ValueError):
    GtkLayerShell = None


def _layer_shell_supported() -> bool:
    display = Gdk.Display.get_default()
    is_wayland = display is not None and display.get_name().startswith("wayland")
    if not is_wayland:
        return True  # X11 positioning via move() works directly
    return GtkLayerShell is not None and GtkLayerShell.is_supported()

_POSITIONS = [
    ("top", "Top, centered"),
    ("center", "Center of screen"),
    ("top-left", "Top left"),
    ("top-right", "Top right"),
]

_THEME_MODES = [
    ("system", "Follow system"),
    ("light", "Light"),
    ("dark", "Dark"),
]

_DENSITIES = [
    ("comfortable", "Comfortable"),
    ("compact", "Compact"),
]

_SEARCH_ENGINES = [
    ("duckduckgo", "DuckDuckGo"),
    ("google", "Google"),
    ("bing", "Bing"),
    ("none", "Disabled"),
]


class SettingsWindow(Gtk.Window):
    """A small modal-ish preferences window. Calls `on_saved(config)` after
    the user applies changes, so the caller can re-apply live appearance."""

    def __init__(self, parent: Gtk.Window, on_saved):
        super().__init__(title="Orbit Launcher Settings")
        self.on_saved = on_saved
        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_resizable(False)
        self.set_default_size(400, 520)
        self.set_border_width(16)

        self.config = load_config()

        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.add(outer)
        outer.pack_start(scroller, True, True, 0)

        grid = Gtk.Grid(row_spacing=10, column_spacing=12)
        grid.set_margin_end(8)
        scroller.add(grid)

        row = 0
        row = self._add_combo(grid, row, "Theme", "theme_mode", _THEME_MODES)

        row = self._add_switch(grid, row, "Transparency", "transparency_enabled")

        self.opacity_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 0.3, 1.0, 0.05
        )
        self.opacity_scale.set_value(self.config["opacity"])
        self.opacity_scale.set_hexpand(True)
        grid.attach(Gtk.Label(label="Opacity", xalign=0), 0, row, 1, 1)
        grid.attach(self.opacity_scale, 1, row, 1, 1)
        row += 1

        row = self._add_switch(
            grid, row, "Blur (experimental, compositor-dependent)", "blur_enabled"
        )

        self.corner_radius_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 0, 30, 1
        )
        self.corner_radius_scale.set_value(self.config["corner_radius"])
        self.corner_radius_scale.set_hexpand(True)
        grid.attach(Gtk.Label(label="Corner roundness", xalign=0), 0, row, 1, 1)
        grid.attach(self.corner_radius_scale, 1, row, 1, 1)
        row += 1

        row = self._add_combo(grid, row, "Window position", "window_position", _POSITIONS)
        if not _layer_shell_supported():
            note = Gtk.Label(
                label=(
                    "Note: your compositor doesn't support the Wayland layer-shell\n"
                    "protocol, so only \u201cCenter\u201d is reliably positioned here;\n"
                    "other options have no effect on stock GNOME/Mutter Wayland."
                ),
                xalign=0,
            )
            note.get_style_context().add_class("dim-label")
            note.set_line_wrap(True)
            grid.attach(note, 0, row, 2, 1)
            row += 1
        row = self._add_combo(grid, row, "Row density", "row_density", _DENSITIES)
        row = self._add_switch(grid, row, "Sync GNOME accent color", "accent_color_sync")
        row = self._add_switch(grid, row, "Fade-in animation", "animate_open")

        row = self._add_switch(grid, row, "Web search fallback", "web_search_enabled")
        row = self._add_combo(grid, row, "Search engine", "web_search_engine", _SEARCH_ENGINES)

        row = self._add_switch(grid, row, "Install suggestions (Software)", "software_install_enabled")
        row = self._add_switch(grid, row, "Recent files", "recent_files_enabled")
        row = self._add_switch(
            grid, row, "Clipboard history (in-memory only, not saved to disk)", "clipboard_history_enabled"
        )

        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        outer.pack_start(footer, False, False, 0)

        about_btn = Gtk.Button(label="About")
        about_btn.connect("clicked", self._on_about)
        footer.pack_start(about_btn, False, False, 0)

        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        button_box.set_halign(Gtk.Align.END)
        footer.pack_end(button_box, False, False, 0)

        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.connect("clicked", lambda *_: self.close())
        button_box.pack_start(cancel_btn, False, False, 0)

        save_btn = Gtk.Button(label="Save")
        save_btn.get_style_context().add_class("suggested-action")
        save_btn.connect("clicked", self._on_save)
        button_box.pack_start(save_btn, False, False, 0)

        self.show_all()

    def _on_about(self, _button):
        dialog = Gtk.AboutDialog(transient_for=self, modal=True)
        dialog.set_program_name("Orbit Launcher")
        dialog.set_version(__version__)
        dialog.set_comments(
            "A fast, keyboard-driven application launcher and calculator for Linux."
        )
        dialog.set_authors(["Orbit Launcher Contributors"])
        dialog.set_license_type(Gtk.License.MIT_X11)
        dialog.set_wrap_license(True)
        dialog.connect("response", lambda widget, _response: widget.destroy())
        dialog.show_all()

    def _add_combo(self, grid, row, label_text, key, options):
        grid.attach(Gtk.Label(label=label_text, xalign=0), 0, row, 1, 1)
        combo = Gtk.ComboBoxText()
        for value, display in options:
            combo.append(value, display)
        combo.set_active_id(self.config.get(key, DEFAULTS.get(key)))
        combo.set_hexpand(True)
        setattr(self, f"_combo_{key}", combo)
        grid.attach(combo, 1, row, 1, 1)
        return row + 1

    def _add_switch(self, grid, row, label_text, key):
        grid.attach(Gtk.Label(label=label_text, xalign=0), 0, row, 1, 1)
        switch = Gtk.Switch()
        switch.set_active(bool(self.config.get(key, DEFAULTS.get(key))))
        switch.set_halign(Gtk.Align.START)
        setattr(self, f"_switch_{key}", switch)
        grid.attach(switch, 1, row, 1, 1)
        return row + 1

    def _on_save(self, _button):
        self.config["theme_mode"] = self._combo_theme_mode.get_active_id()
        self.config["transparency_enabled"] = self._switch_transparency_enabled.get_active()
        self.config["opacity"] = round(self.opacity_scale.get_value(), 2)
        self.config["blur_enabled"] = self._switch_blur_enabled.get_active()
        self.config["corner_radius"] = int(self.corner_radius_scale.get_value())
        self.config["window_position"] = self._combo_window_position.get_active_id()
        self.config["row_density"] = self._combo_row_density.get_active_id()
        self.config["accent_color_sync"] = self._switch_accent_color_sync.get_active()
        self.config["animate_open"] = self._switch_animate_open.get_active()
        self.config["web_search_enabled"] = self._switch_web_search_enabled.get_active()
        self.config["web_search_engine"] = self._combo_web_search_engine.get_active_id()
        self.config["software_install_enabled"] = self._switch_software_install_enabled.get_active()
        self.config["recent_files_enabled"] = self._switch_recent_files_enabled.get_active()
        self.config["clipboard_history_enabled"] = self._switch_clipboard_history_enabled.get_active()

        save_config(self.config)
        if self.on_saved:
            self.on_saved(self.config)
        self.close()
