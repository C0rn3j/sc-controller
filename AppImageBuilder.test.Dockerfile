# syntax=docker/dockerfile:1
ARG BASE_OS=ubuntu
ARG BASE_CODENAME=noble
FROM $BASE_OS:$BASE_CODENAME
WORKDIR /tmp
COPY *.AppImage /opt/
RUN <<EOR
  set -eu

  log() {
    echo >&2 "${@}"
  }

  cancel() {
    log "${@}"
    return 1
  }

  prepare() {
    if command -v apt-get >/dev/null; then
      apt-get update && apt-get install -y --no-install-recommends libx11-6
    elif command -v pacman >/dev/null; then
      pacman -Syu --noconfirm libx11
    elif command -v dnf >/dev/null; then
      dnf list updates && dnf install -y libX11
    fi
  }

  main() {
    files="$(find /opt/ -maxdepth 1 -type f -name '*.AppImage')"
    if [ -z "${files}" ]; then
      cancel "Error: No AppImage file found."
    fi
    prepare
    config_path="${HOME}/.config/scc"
    mkdir -p "${config_path}"
    echo '{}' >"${config_path}/config.json"

    echo "${files}" | while read -r file; do
      log "Testing ${file}"
      chmod +x "${file}"
      rm -rf squashfs-root/
      "${file}" --appimage-extract >/dev/null
      (
        cd squashfs-root/runtime/compat
        ../../AppRun dependency-check
        ../../AppRun daemon --help
      )
      rm -f "${file}"
    done
  }
  main "${@}"
EOR
