Name:           launcher
Version:        0.2.5
Release:        1%{?dist}
Summary:        Orbit Launcher: a GTK-themed desktop launcher and search tool

License:        MIT
URL:            https://github.com/%{name}/%{name}
Source0:        %{name}-%{version}.tar.gz

BuildArch:      noarch

BuildRequires:  python3-devel
BuildRequires:  pyproject-rpm-macros
BuildRequires:  python3-pip
BuildRequires:  python3-gobject
BuildRequires:  gtk3
BuildRequires:  desktop-file-utils

Requires:       python3-gobject
Requires:       gtk3
Requires:       gtk-layer-shell
Requires:       hicolor-icon-theme

%global desktop_file %{name}.desktop

%description
Orbit Launcher is a fast, keyboard-driven application launcher and
calculator for the Linux desktop. It uses standard GTK widgets and CSS
theming so it automatically follows your system GTK theme, and supports a
user override stylesheet in ~/.config/launcher/style.css.

Bind the `launcher` or `orbit` command to a keyboard shortcut in your
desktop environment to toggle the search popup on demand.

%prep
%autosetup -n %{name}-%{version}

%generate_buildrequires
%pyproject_buildrequires

%build
%pyproject_wheel

%install
%pyproject_install
%pyproject_save_files launcher

install -Dm0644 packaging/io.github.orbit.OrbitLauncher.desktop \
    %{buildroot}%{_datadir}/applications/io.github.orbit.OrbitLauncher.desktop

desktop-file-validate %{buildroot}%{_datadir}/applications/io.github.orbit.OrbitLauncher.desktop

%files -f %{pyproject_files}
%license LICENSE
%doc README.md
%{_bindir}/launcher
%{_bindir}/orbit
%{_datadir}/applications/io.github.orbit.OrbitLauncher.desktop

%changelog
* Sat Sep 19 2026 Orbit Launcher Contributors <noreply@example.com> - 0.1.0-1
- Initial package
