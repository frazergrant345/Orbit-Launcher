"""Search backends: installed applications and a simple calculator."""
import ast
import math
import operator
import urllib.parse
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Callable, List, Optional

import gi

gi.require_version("Gio", "2.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gio, GLib, Gtk

from .config import SEARCH_ENGINE_URLS


@dataclass
class Result:
    title: str
    subtitle: str
    icon_name: str
    action: Callable[[], None]
    score: float = 0.0
    kind: str = "App"
    result_id: Optional[str] = None


class AppProvider:
    """Searches installed .desktop applications."""

    def __init__(self):
        self._apps = []
        self.refresh()

    def refresh(self):
        apps = Gio.AppInfo.get_all()
        self._apps = [a for a in apps if a.should_show()]

    def search(self, query: str, limit: int) -> List[Result]:
        query = query.strip().lower()
        if not query:
            return []

        scored = []
        for app in self._apps:
            name = (app.get_display_name() or "").lower()
            if not name:
                continue
            score = _match_score(query, name)
            if score <= 0:
                keywords = app.get_keywords() if hasattr(app, "get_keywords") else []
                for kw in keywords:
                    score = max(score, _match_score(query, kw.lower()) * 0.8)
            if score > 0:
                scored.append((score, app))

        scored.sort(key=lambda pair: pair[0], reverse=True)

        results = []
        for score, app in scored[:limit]:
            icon = app.get_icon()
            icon_name = icon.to_string() if icon else "application-x-executable"
            results.append(
                Result(
                    title=app.get_display_name() or app.get_name(),
                    subtitle=app.get_description() or app.get_executable() or "",
                    icon_name=icon_name,
                    action=lambda app=app: app.launch([], None),
                    score=score,
                    kind="App",
                    result_id=f"app:{app.get_id() or app.get_name()}",
                )
            )
        return results


# --- System settings panels --------------------------------------------

# (title, panel_id for `gnome-control-center <panel_id>`, icon, keywords)
_SETTINGS_PANELS = [
    ("Wi-Fi", "wifi", "network-wireless-symbolic", ["wireless", "network"]),
    ("Network", "network", "network-wired-symbolic", ["ethernet", "vpn", "proxy"]),
    ("Bluetooth", "bluetooth", "bluetooth-symbolic", []),
    ("Displays", "display", "video-display-symbolic", ["monitor", "resolution", "screen"]),
    ("Sound", "sound", "audio-speakers-symbolic", ["audio", "volume", "speakers", "microphone"]),
    ("Power", "power", "battery-symbolic", ["battery", "energy"]),
    ("Keyboard Shortcuts", "keyboard", "input-keyboard-symbolic", ["shortcuts", "shortcut", "keybinding"]),
    ("Mouse & Touchpad", "mouse", "input-mouse-symbolic", ["touchpad", "trackpad", "pointer"]),
    ("Notifications", "notifications", "preferences-system-notifications-symbolic", ["notify", "dnd", "do not disturb"]),
    ("Privacy", "privacy", "preferences-system-privacy-symbolic", ["location", "camera", "microphone permissions"]),
    ("Background", "background", "preferences-desktop-wallpaper-symbolic", ["wallpaper"]),
    ("Appearance", "appearance", "preferences-desktop-theme-symbolic", ["theme", "dark mode", "light mode", "style"]),
    ("Users", "user-accounts", "system-users-symbolic", ["accounts", "user accounts"]),
    ("Date & Time", "datetime", "preferences-system-time-symbolic", ["clock", "timezone"]),
    ("Region & Language", "region", "preferences-desktop-locale-symbolic", ["language", "locale"]),
    ("Online Accounts", "online-accounts", "goa-panel-symbolic", ["google account", "email account"]),
    ("Sharing", "sharing", "preferences-system-sharing-symbolic", ["screen sharing", "remote desktop"]),
    ("Printers", "printers", "printer-symbolic", ["printer", "printing"]),
    ("Accessibility", "universal-access", "preferences-desktop-accessibility-symbolic", ["universal access"]),
    ("Multitasking", "multitasking", "preferences-system-windows-symbolic", ["workspaces", "hot corner"]),
    ("Default Applications", "applications", "preferences-desktop-apps-symbolic", ["default apps"]),
    ("About This System", "system", "help-about-symbolic", ["system info", "hardware info", "about"]),
]


class SettingsProvider:
    """Searches system settings panels (via gnome-control-center)."""

    def __init__(self):
        self._binary = GLib.find_program_in_path("gnome-control-center")

    def search(self, query: str, limit: int) -> List[Result]:
        query = query.strip().lower()
        if not query or not self._binary:
            return []

        scored = []
        for title, panel_id, icon_name, keywords in _SETTINGS_PANELS:
            score = _match_score(query, title.lower())
            for kw in keywords:
                score = max(score, _match_score(query, kw.lower()))
            if score > 0:
                scored.append((score, title, panel_id, icon_name))

        scored.sort(key=lambda item: item[0], reverse=True)

        results = []
        for score, title, panel_id, icon_name in scored[:limit]:
            results.append(
                Result(
                    title=title,
                    subtitle="System Settings",
                    icon_name=icon_name,
                    action=lambda panel_id=panel_id: self._open_panel(panel_id),
                    score=score * 0.95,  # slightly below equally-scored apps
                    kind="Setting",
                    result_id=f"settings:{panel_id}",
                )
            )
        return results

    def _open_panel(self, panel_id: str):
        try:
            Gio.Subprocess.new([self._binary, panel_id], Gio.SubprocessFlags.NONE)
        except GLib.Error:
            pass


def _match_score(query: str, target: str) -> float:
    if not target:
        return 0.0
    if target == query:
        return 100.0
    if target.startswith(query):
        return 80.0
    if query in target:
        return 60.0
    ratio = SequenceMatcher(None, query, target).ratio()
    return ratio * 40.0 if ratio > 0.6 else 0.0


# --- Calculator -------------------------------------------------------

_ALLOWED_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_ALLOWED_UNARYOPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}
_ALLOWED_NAMES = {
    "pi": math.pi,
    "e": math.e,
}
_ALLOWED_FUNCS = {
    "sqrt": math.sqrt,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "log": math.log,
    "log10": math.log10,
    "abs": abs,
    "round": round,
}


def _eval_node(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_BINOPS:
        return _ALLOWED_BINOPS[type(node.op)](_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_UNARYOPS:
        return _ALLOWED_UNARYOPS[type(node.op)](_eval_node(node.operand))
    if isinstance(node, ast.Name) and node.id in _ALLOWED_NAMES:
        return _ALLOWED_NAMES[node.id]
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _ALLOWED_FUNCS:
        args = [_eval_node(a) for a in node.args]
        return _ALLOWED_FUNCS[node.func.id](*args)
    raise ValueError("unsupported expression")


def try_calculate(expression: str) -> Optional[str]:
    """Safely evaluate a simple arithmetic expression, returning a display
    string, or None if the input doesn't look like a calculation."""
    expression = expression.strip()
    if not expression or not any(ch.isdigit() for ch in expression):
        return None
    try:
        tree = ast.parse(expression, mode="eval")
        value = _eval_node(tree.body)
    except (SyntaxError, ValueError, ZeroDivisionError, TypeError):
        return None

    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value)


# --- Web search fallback ----------------------------------------------


def build_web_search_result(query: str, engine: str) -> Optional[Result]:
    """Build a Result that opens the default browser to search `query`."""
    template = SEARCH_ENGINE_URLS.get(engine)
    if not template or not query.strip():
        return None

    url = template.format(query=urllib.parse.quote_plus(query.strip()))

    def _open():
        try:
            Gio.AppInfo.launch_default_for_uri(url, None)
        except GLib.Error:
            pass

    return Result(
        title=f"Search the web for \u201c{query}\u201d",
        subtitle=url,
        icon_name="web-browser",
        action=_open,
        score=-1,
        kind="Web",
    )


# --- Unit conversion ----------------------------------------------------

_UNIT_GROUPS = {
    # length, in meters
    "mm": ("length", 0.001), "cm": ("length", 0.01), "m": ("length", 1.0),
    "km": ("length", 1000.0), "in": ("length", 0.0254), "ft": ("length", 0.3048),
    "yd": ("length", 0.9144), "mi": ("length", 1609.344), "miles": ("length", 1609.344),
    # mass, in kilograms
    "mg": ("mass", 1e-6), "g": ("mass", 0.001), "kg": ("mass", 1.0),
    "lb": ("mass", 0.453592), "lbs": ("mass", 0.453592), "oz": ("mass", 0.0283495),
    # volume, in liters
    "ml": ("volume", 0.001), "l": ("volume", 1.0), "gal": ("volume", 3.78541),
    "cup": ("volume", 0.236588), "cups": ("volume", 0.236588),
    # data, in bytes
    "kb": ("data", 1000), "mb": ("data", 1000**2), "gb": ("data", 1000**3),
    "kib": ("data", 1024), "mib": ("data", 1024**2), "gib": ("data", 1024**3),
}

_CONVERT_RE = None


def try_convert(expression: str) -> Optional[str]:
    """Handle simple unit conversions like `10 km in miles` or `5 lb to kg`.
    Temperature (c/f/k) is handled separately since it isn't a linear ratio."""
    global _CONVERT_RE
    if _CONVERT_RE is None:
        import re

        _CONVERT_RE = re.compile(
            r"^\s*([\d.]+)\s*([a-zA-Z]+)\s+(?:in|to)\s+([a-zA-Z]+)\s*$"
        )

    match = _CONVERT_RE.match(expression)
    if not match:
        return None

    value_str, from_unit, to_unit = match.groups()
    try:
        value = float(value_str)
    except ValueError:
        return None
    from_unit, to_unit = from_unit.lower(), to_unit.lower()

    temp_result = _try_convert_temperature(value, from_unit, to_unit)
    if temp_result is not None:
        return temp_result

    from_info = _UNIT_GROUPS.get(from_unit)
    to_info = _UNIT_GROUPS.get(to_unit)
    if not from_info or not to_info or from_info[0] != to_info[0]:
        return None

    base_value = value * from_info[1]
    result = base_value / to_info[1]
    return f"{result:g} {to_unit}"


_TEMP_UNITS = {"c", "celsius", "f", "fahrenheit", "k", "kelvin"}


def _try_convert_temperature(value, from_unit, to_unit):
    if from_unit not in _TEMP_UNITS or to_unit not in _TEMP_UNITS:
        return None

    def to_celsius(v, unit):
        if unit in ("c", "celsius"):
            return v
        if unit in ("f", "fahrenheit"):
            return (v - 32) * 5.0 / 9.0
        return v - 273.15  # kelvin

    def from_celsius(v, unit):
        if unit in ("c", "celsius"):
            return v
        if unit in ("f", "fahrenheit"):
            return v * 9.0 / 5.0 + 32
        return v + 273.15  # kelvin

    celsius = to_celsius(value, from_unit)
    result = from_celsius(celsius, to_unit)
    return f"{result:g} \u00b0{to_unit[0].upper()}"


# --- Recent files ---------------------------------------------------------


class RecentFilesProvider:
    """Searches recently opened files via GLib's recently-used registry."""

    def search(self, query: str, limit: int) -> List[Result]:
        query = query.strip().lower()
        if not query:
            return []

        manager = Gtk.RecentManager.get_default()
        scored = []
        for item in manager.get_items():
            if not item.exists():
                continue
            name = item.get_display_name() or ""
            score = _match_score(query, name.lower())
            if score > 0:
                scored.append((score, item))

        scored.sort(key=lambda pair: pair[0], reverse=True)

        results = []
        for score, item in scored[:limit]:
            uri = item.get_uri()
            icon = item.get_gicon()
            icon_name = icon.to_string() if icon else "text-x-generic"
            results.append(
                Result(
                    title=item.get_display_name(),
                    subtitle=item.get_uri_display() or uri,
                    icon_name=icon_name,
                    action=lambda uri=uri: _open_uri(uri),
                    score=score * 0.9,
                    kind="File",
                    result_id=f"file:{uri}",
                )
            )
        return results


def _open_uri(uri: str):
    try:
        Gio.AppInfo.launch_default_for_uri(uri, None)
    except GLib.Error:
        pass


# --- Install from the software center -------------------------------------

_SOFTWARE_CENTER_CANDIDATES = [
    ("gnome-software", ["--search={query}"]),
    ("plasma-discover", ["--search", "{query}"]),
    ("snap-store", ["--search={query}"]),
]


class SoftwareCenterProvider:
    """Offers to search/install software when nothing installed matches."""

    def __init__(self):
        self._binary = None
        self._args_template = None
        for name, args in _SOFTWARE_CENTER_CANDIDATES:
            path = GLib.find_program_in_path(name)
            if path:
                self._binary = path
                self._args_template = args
                break

    @property
    def available(self) -> bool:
        return self._binary is not None

    def build_result(self, query: str) -> Optional[Result]:
        query = query.strip()
        if not query or not self._binary:
            return None

        args = [a.format(query=query) for a in self._args_template]

        def _open():
            try:
                Gio.Subprocess.new([self._binary, *args], Gio.SubprocessFlags.NONE)
            except GLib.Error:
                pass

        return Result(
            title=f"Search for \u201c{query}\u201d in Software",
            subtitle="Install from the software center",
            icon_name="system-software-install",
            action=_open,
            score=-2,
            kind="Software",
        )


# --- Custom snippets & shell commands --------------------------------------


class SnippetProvider:
    """User-defined keyword shortcuts, e.g. `gh myrepo` -> a GitHub URL."""

    def __init__(self, snippets):
        self._snippets = snippets or []

    def search(self, query: str) -> List[Result]:
        stripped = query.strip()
        if not stripped or " " not in stripped:
            return []

        keyword, _, rest = stripped.partition(" ")
        results = []
        for snippet in self._snippets:
            if snippet.get("keyword", "").lower() != keyword.lower():
                continue
            url_template = snippet.get("url", "")
            if not url_template:
                continue
            url = url_template.replace("{query}", urllib.parse.quote(rest.strip(), safe="/"))

            def _open(url=url):
                try:
                    Gio.AppInfo.launch_default_for_uri(url, None)
                except GLib.Error:
                    pass

            results.append(
                Result(
                    title=f"{keyword} {rest}".strip(),
                    subtitle=url,
                    icon_name="text-x-generic-symbolic",
                    action=_open,
                    score=500,
                    kind="Snippet",
                )
            )
        return results


def build_shell_command_result(query: str) -> Optional[Result]:
    """Handle a `> command` prefix as a one-off shell command to run."""
    if not query.startswith(">"):
        return None
    command = query[1:].strip()
    if not command:
        return None

    def _run():
        try:
            Gio.Subprocess.new(["/bin/sh", "-c", command], Gio.SubprocessFlags.NONE)
        except GLib.Error:
            pass

    return Result(
        title=f"Run: {command}",
        subtitle="Shell command",
        icon_name="utilities-terminal",
        action=_run,
        score=1000,
        kind="Shell",
    )


# --- Clipboard history (in-memory only, never written to disk) ------------


class ClipboardHistory:
    def __init__(self, max_items: int = 25):
        self._items: List[str] = []
        self._max_items = max_items

    def add(self, text: str):
        text = text.strip()
        if not text:
            return
        if self._items and self._items[0] == text:
            return
        if text in self._items:
            self._items.remove(text)
        self._items.insert(0, text)
        del self._items[self._max_items:]

    def search(self, query: str, limit: int) -> List[Result]:
        query = query.strip().lower()
        if not query:
            return []

        scored = []
        for text in self._items:
            score = _match_score(query, text.lower())
            if score > 0:
                scored.append((score, text))
        scored.sort(key=lambda pair: pair[0], reverse=True)

        results = []
        for score, text in scored[:limit]:
            preview = text if len(text) <= 60 else text[:57] + "..."
            results.append(
                Result(
                    title=preview,
                    subtitle="Clipboard history",
                    icon_name="edit-paste-symbolic",
                    action=lambda text=text: _copy_text(text),
                    score=score * 0.85,
                    kind="Clipboard",
                )
            )
        return results


def _copy_text(text: str):
    from gi.repository import Gdk, Gtk

    clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
    clipboard.set_text(text, -1)
    clipboard.store()
