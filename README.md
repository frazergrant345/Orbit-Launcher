# Orbit Launcher

A fast, keyboard-driven application launcher and calculator for Linux,
similar to [Ulauncher](https://ulauncher.io/). Built with GTK3 / PyGObject,
so it automatically follows your system GTK theme.

## Features

- Fuzzy search over installed applications (`.desktop` entries)
- Inline calculator (`2 * (3 + 4)`, `sqrt(2)`, results copied to clipboard)
- Fully GTK-themed: uses your system GTK theme's colors automatically
- User-overridable CSS at `~/.config/launcher/style.css`
- Single-instance app: running `launcher` again just toggles the popup,
  so you can bind it to a global keyboard shortcut in your DE

## Running from source

```bash
# Fedora dependencies
sudo dnf install python3-gobject gtk3

python3 -m launcher.app
```

Then, in your desktop environment's keyboard shortcut settings, bind a key
combo (e.g. `Super+Space`) to run `orbit` or `launcher`. Running it again
while the popup is open will hide it.

## Theming

Orbit Launcher uses standard GTK widgets styled with CSS classes such as
`.launcher-window`, `.launcher-entry`, `.launcher-result-row`. The bundled
default stylesheet references GTK theme colors (`@theme_bg_color`,
`@theme_selected_bg_color`, etc.) so switching your system GTK theme
changes the launcher's look automatically.

To customise further, edit `~/.config/launcher/style.css` (created
automatically on first run) — it's loaded with `GTK_STYLE_PROVIDER_PRIORITY_USER`,
so it overrides the bundled defaults.

## Configuration

Settings live in `~/.config/launcher/config.json`:

```json
{
  "max_results": 8,
  "window_width": 640,
  "icon_size": 32,
  "show_descriptions": true
}
```

## Building an RPM (Fedora)

```bash
sudo dnf install rpmdevtools pyproject-rpm-macros python3-devel
make rpm
```

The built RPM will be under `~/rpmbuild/RPMS/noarch/`. Install it with:

```bash
sudo dnf install ~/rpmbuild/RPMS/noarch/launcher-0.2.5-1.*.rpm
```
