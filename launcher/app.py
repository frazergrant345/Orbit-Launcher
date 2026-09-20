"""Application entry point.

Uses Gtk.Application's built-in single-instance behaviour: running the
`launcher` binary while an instance is already active simply re-activates
that instance (do_activate is called again), which we use to toggle the
popup's visibility. Bind this command to a keyboard shortcut in your
desktop environment's settings to get a global hotkey.
"""
import sys
from importlib import resources

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gio, GLib, Gtk

from .config import ensure_user_css
from .window import LauncherWindow

APP_ID = "io.github.orbit.OrbitLauncher"


class LauncherApplication(Gtk.Application):
    def __init__(self):
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.FLAGS_NONE,
        )
        self.window = None

    def do_startup(self):
        Gtk.Application.do_startup(self)
        self._load_css()

    def do_activate(self):
        if self.window is None:
            self.window = LauncherWindow(self)

        if self.window.is_visible():
            self.window.hide()
        else:
            self.window.present_and_focus()

    def restart_window(self):
        """Destroy and recreate the popup window.

        Some appearance settings (e.g. the RGBA visual needed for
        transparency) can only be applied before a window is first realized,
        so the reliable way to make every setting take effect is to rebuild
        the window rather than mutate the live one."""
        if self.window is not None:
            self.window.destroy()
        self.window = LauncherWindow(self)
        self.window.present_and_focus()

    def _load_css(self):
        screen = Gdk.Screen.get_default()

        default_provider = Gtk.CssProvider()
        default_css = resources.files("launcher.data").joinpath("style-default.css").read_bytes()
        default_provider.load_from_data(default_css)
        Gtk.StyleContext.add_provider_for_screen(
            screen, default_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        user_css_path = ensure_user_css()
        user_provider = Gtk.CssProvider()
        try:
            user_provider.load_from_path(str(user_css_path))
            Gtk.StyleContext.add_provider_for_screen(
                screen, user_provider, Gtk.STYLE_PROVIDER_PRIORITY_USER
            )
        except GLib.Error:
            pass


def main():
    app = LauncherApplication()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
