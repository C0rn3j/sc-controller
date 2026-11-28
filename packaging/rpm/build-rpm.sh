#!/usr/bin/env bash
# Build SC Controller RPMs for Fedora inside a container (podman or docker).
# Usage: packaging/rpm/build-rpm.sh [fedora_release]   (default 45)
# Output: ./rpm-out/
set -euo pipefail

FEDORA="${1:-${FEDORA_RELEASE:-45}}"
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo"

engine="${CONTAINER_ENGINE:-$(command -v podman || command -v docker || true)}"
[ -n "$engine" ] || { echo "Need podman or docker installed" >&2; exit 1; }

# Derive version from git tags (v0.6.2 or v0.6.2-15-gabcdef).
# With no usable tag (e.g. a fork without upstream tags) fall back to 0.0.1.post<commits>.
version="0.0.1"; snapshot=""; scm="0.0.1"
if desc="$(git describe --tags --long --match 'v[0-9]*' 2>/dev/null)" \
		&& [[ "$desc" =~ ^v([0-9][0-9.]*)-([0-9]+)-g([0-9a-f]+)$ ]]; then
	version="${BASH_REMATCH[1]}"; n="${BASH_REMATCH[2]}"; h="${BASH_REMATCH[3]}"
elif git rev-parse --git-dir >/dev/null 2>&1; then
	n="$(git rev-list --count HEAD)"; h="$(git rev-parse --short HEAD)"
else
	n=0; h=""
fi
if [ "${n:-0}" != "0" ]; then
	snapshot="${n}.git${h}"
	scm="${version}.post${n}+g${h}"
else
	scm="$version"
fi
echo "Building sc-controller ${version} ${snapshot} for Fedora ${FEDORA} using $(basename "$engine")"

# Source tarball from the working tree (tracked + untracked, honouring .gitignore)
rm -rf dist-rpm rpm-out; mkdir -p dist-rpm rpm-out
if git rev-parse --git-dir >/dev/null 2>&1; then
	git ls-files -z --cached --others --exclude-standard \
		| tar --null -T - --ignore-failed-read 2>/dev/null \
			--transform "flags=r;s,^,sc-controller-${version}/," \
			-czf "dist-rpm/sc-controller-${version}.tar.gz"
else
	tar --exclude=./dist-rpm --exclude=./rpm-out --exclude=./.venv --exclude=./build --exclude=./dist \
		--transform "flags=r;s,^\.,sc-controller-${version}," \
		-czf "dist-rpm/sc-controller-${version}.tar.gz" .
fi

"$engine" run --rm \
	-v "$repo:/src:ro,Z" \
	-v "$repo/rpm-out:/out:Z" \
	-e SCC_VERSION="$version" -e SCC_SNAPSHOT="$snapshot" -e SCC_SCM_VERSION="$scm" \
	"registry.fedoraproject.org/fedora:${FEDORA}" \
	bash /src/packaging/rpm/container-build.sh

rm -rf dist-rpm
echo "RPMs written to $repo/rpm-out/"
