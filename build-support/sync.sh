#!/usr/bin/env bash
set -euo pipefail
umask 077
cd /src
state=/work/state
mkdir -p "$state"
trap 'rc=$?; printf "%s\n" "$rc" > "$state/sync.exit"' EXIT
export GIT_TERMINAL_PROMPT=0
export REPO_SKIP_SELF_UPDATE=1
export GIT_CONFIG_COUNT=2
export GIT_CONFIG_KEY_0=user.name
export GIT_CONFIG_VALUE_0='Local Karat Build'
export GIT_CONFIG_KEY_1=user.email
export GIT_CONFIG_VALUE_1='karat-build@localhost.invalid'
printf '%s\n' initializing > "$state/sync.phase"
repo init -u https://github.com/LineageOS/android.git \
    -b 569c0d5ee26a7ebbda1e1bd91dc6f7e392c67fd7 \
    --depth=1 --git-lfs --no-clone-bundle
if test -f /work/port/manifests/karat-pinned.xml; then
    cp /work/port/manifests/karat-pinned.xml .repo/manifests/karat-pinned.xml
    repo init -m karat-pinned.xml
fi

# Make the build configuration available early for inspection while the
# remaining platform source downloads. No image is built or flashed here.
printf '%s\n' core-sync > "$state/sync.phase"
repo sync -c -j4 --no-tags --no-clone-bundle \
    build/make build/soong build/blueprint build/bazel \
    prebuilts/build-tools prebuilts/go/linux-x86 \
    vendor/lineage device/google/atv device/lineage/atv \
    system/sepolicy hardware/interfaces system/core
printf '%s\n' full-sync > "$state/sync.phase"
repo sync -c -j8 --no-tags --no-clone-bundle
repo manifest -r -o "$state/manifest-pinned.xml"
printf '%s\n' complete > "$state/sync.phase"
