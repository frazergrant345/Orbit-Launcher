"""Configuration handling for launcher.

Reads a JSON config from ~/.config/launcher/config.json, creating a default
one on first run. Also resolves the path to an optional user CSS override
(~/.config/launcher/style.css) used for GTK theming customisation.
"""
import json
import os
from pathlib import Path

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "launcher"
CONFIG_FILE = CONFIG_DIR / "config.json"
USER_CSS_FILE = CONFIG_DIR / "style.css"
USAGE_FILE = CONFIG_DIR / "usage.json"

DEFAULTS = {
    "max_results": 8,
    "window_width": 760,
    "icon_size": 36,
    "show_descriptions": True,
    "row_density": "comfortable",  # "comfortable" | "compact"
    # Appearance
    "theme_mode": "system",       # "system" | "light" | "dark"
    "transparency_enabled": False,
    "opacity": 0.95,               # 0.3 - 1.0
    "blur_enabled": False,         # experimental, compositor-dependent (e.g. KWin)
    "corner_radius": 18,           # px
    "window_position": "top",      # "top" | "center" | "top-left" | "top-right"
    "accent_color_sync": True,      # follow GNOME's system accent color when available
    "animate_open": True,
    # Web search fallback
    "web_search_enabled": True,
    "web_search_engine": "duckduckgo",  # "google" | "duckduckgo" | "bing" | "none"
    # Extra providers
    "software_install_enabled": True,
    "recent_files_enabled": True,
    "clipboard_history_enabled": False,  # opt-in: history is in-memory only, never saved to disk
    "snippets": [],  # [{"keyword": "gh", "url": "https://github.com/{query}"}]
}

SEARCH_ENGINE_URLS = {
    "google": "https://www.google.com/search?q={query}",
    "duckduckgo": "https://duckduckgo.com/?q={query}",
    "bing": "https://www.bing.com/search?q={query}",
}



def load_config() -> dict:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_FILE.exists():
        CONFIG_FILE.write_text(json.dumps(DEFAULTS, indent=2) + "\n")
        return dict(DEFAULTS)

    try:
        data = json.loads(CONFIG_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULTS)

    merged = dict(DEFAULTS)
    merged.update(data)
    return merged


def save_config(config: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    merged = dict(DEFAULTS)
    merged.update(config)
    CONFIG_FILE.write_text(json.dumps(merged, indent=2) + "\n")


def ensure_user_css() -> Path:
    """Create an empty user CSS override file the first time, so users have
    an obvious place to add GTK theme tweaks without touching packaged files."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not USER_CSS_FILE.exists():
        USER_CSS_FILE.write_text(
            "/* Add custom GTK CSS here to override the launcher theme.\n"
            " * This file takes priority over the bundled default style. */\n"
        )
    return USER_CSS_FILE
