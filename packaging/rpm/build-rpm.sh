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

# Derive version from git tags (v0.6.2 or v0.6.2-15-gabcdef), else fall back.
version="0.0.0"; snapshot=""; scm="0.0.0"
if desc="$(git describe --tags --long --match 'v[0-9]*' 2>/dev/null)"; then
	if [[ "$desc" =~ ^v([0-9][0-9.]*)-([0-9]+)-g([0-9a-f]+)$ ]]; then
		version="${BASH_REMATCH[1]}"
		if [ "${BASH_REMATCH[2]}" != "0" ]; then
			snapshot="${BASH_REMATCH[2]}.git${BASH_REMATCH[3]}"
			scm="${version}.post${BASH_REMATCH[2]}+g${BASH_REMATCH[3]}"
		else
			scm="$version"
		fi
	fi
fi
echo "Building sc-controller ${version} ${snapshot} for Fedora ${FEDORA} using $(basename "$engine")"

# Source tarball from the working tree (tracked + untracked, honouring .gitignore)
rm -rf dist-rpm rpm-out; mkdir -p dist-rpm rpm-out
if git rev-parse --git-dir >/dev/null 2>&1; then
	git ls-files -z --cached --others --exclude-standard \
		| tar --null -T - --ignore-failed-read 2>/dev/null \
			--transform "s,^,sc-controller-${version}/," \
			-czf "dist-rpm/sc-controller-${version}.tar.gz"
else
	tar --exclude=./dist-rpm --exclude=./rpm-out --exclude=./.venv --exclude=./build --exclude=./dist \
		--transform "s,^\.,sc-controller-${version}," \
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
