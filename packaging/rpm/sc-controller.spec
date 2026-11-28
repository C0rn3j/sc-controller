# RPM spec for SC Controller, targeting Fedora 45 (Python 3.15).
# Normally driven by packaging/rpm/build-rpm.sh, which supplies these defines:
#   scc_version   - upstream version, e.g. 0.6.2
#   scc_snapshot  - optional, e.g. 15.gabcdef1 for builds past a tag
#   scc_scm_version - exact PEP 440 version handed to setuptools-scm
# Untagged builds must not normalise to 0 or rpm refuses to build
%global _python_dist_allow_version_zero 1
%{!?scc_version: %global scc_version 0.0.1}
%{!?scc_scm_version: %global scc_scm_version %{scc_version}}

# ioctl-opt is not packaged in Fedora, so by default it is pulled from PyPI
# during %%install and shipped inside this package.
# Use `rpmbuild --without bundled_ioctl_opt` if python3-ioctl-opt exists.
%bcond bundled_ioctl_opt 1
# Run the pytest suite under xvfb: `rpmbuild --with tests`
%bcond tests 0

Name:           sc-controller
Version:        %{scc_version}
Release:        1%{?scc_snapshot:.%{scc_snapshot}}%{?dist}
Summary:        User-mode driver, mapper and GTK4 GUI for Steam Controller, DS4 and similar controllers
License:        GPL-2.0-only
URL:            https://github.com/C0rn3j/sc-controller
Source0:        %{name}-%{version}.tar.gz

BuildRequires:  gcc
BuildRequires:  gettext
BuildRequires:  python3-devel
BuildRequires:  python3-pip
BuildRequires:  python3-setuptools
BuildRequires:  python3-setuptools_scm
BuildRequires:  python3-wheel
BuildRequires:  pyproject-rpm-macros
BuildRequires:  bluez-libs-devel
BuildRequires:  zlib-devel
BuildRequires:  desktop-file-utils
BuildRequires:  appstream
BuildRequires:  systemd-rpm-macros
%if %{with tests}
BuildRequires:  python3-pytest
BuildRequires:  xorg-x11-server-Xvfb
BuildRequires:  python3-evdev
BuildRequires:  python3-libusb1
BuildRequires:  python3-vdf
BuildRequires:  python3-gobject
BuildRequires:  python3-cairo
BuildRequires:  gtk4
BuildRequires:  gtk4-layer-shell
BuildRequires:  librsvg2
%endif

Requires:       gtk4
Requires:       gtk4-layer-shell
Requires:       librsvg2
Requires:       bluez-libs
Requires:       python3-gobject
Requires:       python3-cairo
Requires:       python3-evdev
Requires:       python3-libusb1
Requires:       python3-vdf
%if %{without bundled_ioctl_opt}
BuildRequires:  python3-ioctl-opt
Requires:       python3-ioctl-opt
%endif
Requires:       hicolor-icon-theme
%{?systemd_requires}

%description
SC Controller is a user-mode driver, mapper and GTK4 based GUI for the
Steam Controller, DualShock 4, DualSense and similar game controllers.

%prep
%autosetup -n %{name}-%{version}

%build
export SETUPTOOLS_SCM_PRETEND_VERSION='%{scc_scm_version}'
%pyproject_wheel

%install
export SETUPTOOLS_SCM_PRETEND_VERSION='%{scc_scm_version}'
%pyproject_install

%if %{with bundled_ioctl_opt}
# Needs network access (fine for local container and GitHub builds, not for
# offline mock/COPR builds - use --without bundled_ioctl_opt there).
%{python3} -m pip install --no-deps --no-compile --disable-pip-version-check \
    --root %{buildroot} --prefix %{_prefix} ioctl-opt
rm -f %{buildroot}%{python3_sitelib}/ioctl_opt-*.dist-info/{INSTALLER,REQUESTED,direct_url.json}
%py_byte_compile %{python3} %{buildroot}%{python3_sitelib}/ioctl_opt*
%endif

%check
desktop-file-validate %{buildroot}%{_datadir}/applications/io.github.c0rn3j.sc-controller.desktop
appstreamcli validate --no-net %{buildroot}%{_metainfodir}/io.github.c0rn3j.sc-controller.metainfo.xml || :
%if %{with tests}
export PYTHONPATH=%{buildroot}%{python3_sitearch}:%{buildroot}%{python3_sitelib}
export SCC_SHARED=%{buildroot}%{_datadir}/scc
xvfb-run -a %{python3} -m pytest tests
%endif

%post
%udev_rules_update

%postun
%udev_rules_update

%files
%license LICENSE ADDITIONAL-LICENSES
%doc README.md
%{_bindir}/sc-controller
%{_bindir}/scc
%{_bindir}/scc-*
%{python3_sitearch}/scc/
%{python3_sitearch}/lib*.so
%{python3_sitearch}/sccontroller-*.dist-info/
%if %{with bundled_ioctl_opt}
%{python3_sitelib}/ioctl_opt*
%endif
%{_datadir}/scc/
%{_datadir}/locale/*/LC_MESSAGES/sc-controller.mo
%{_datadir}/applications/io.github.c0rn3j.sc-controller.desktop
%{_datadir}/icons/hicolor/*/*/*
%{_metainfodir}/io.github.c0rn3j.sc-controller.metainfo.xml
%{_datadir}/mime/packages/io.github.c0rn3j.sc-controller.mimetypes.xml
%{_prefix}/lib/udev/rules.d/69-sc-controller.rules

%changelog
* Sat Nov 28 2026 Packager <packager@example.com> - %{version}-%{release}
- Initial RPM packaging for Fedora 45
