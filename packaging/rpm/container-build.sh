#!/usr/bin/env bash
# Runs INSIDE a fedora container. Expects:
#   /src/packaging/rpm/sc-controller.spec, /src/dist-rpm/sc-controller-<ver>.tar.gz
#   env: SCC_VERSION SCC_SNAPSHOT SCC_SCM_VERSION
# Writes RPMs to /out
set -euo pipefail

dnf -y install rpm-build rpmdevtools dnf-plugins-core python3-devel pyproject-rpm-macros
spec=/src/packaging/rpm/sc-controller.spec
defs=(--define "scc_version ${SCC_VERSION}" --define "scc_scm_version ${SCC_SCM_VERSION}")
[ -n "${SCC_SNAPSHOT:-}" ] && defs+=(--define "scc_snapshot ${SCC_SNAPSHOT}")

dnf -y builddep "${defs[@]}" "$spec"

rpmdev-setuptree
cp /src/dist-rpm/sc-controller-"${SCC_VERSION}".tar.gz ~/rpmbuild/SOURCES/
rpmbuild -ba "${defs[@]}" "$spec"

mkdir -p /out
find ~/rpmbuild/RPMS ~/rpmbuild/SRPMS -name '*.rpm' -exec cp -v {} /out/ \;
