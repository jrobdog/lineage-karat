#!/usr/bin/env bash
# Container entry point. Output is a development image, not an installer.
set -euo pipefail
umask 077
cd /src
test "$(cat /work/state/sync.phase)" = complete
test "$(cat /work/state/sync.exit)" = 0
test -s /work/state/manifest-pinned.xml
test -f device/amazon/karat/lineage_karat.mk
export TARGET_PRODUCT=lineage_karat
export TARGET_BUILD_VARIANT=userdebug
export TARGET_BUILD_TYPE=release
export LINEAGE_BUILD=karat
export LINEAGE_VERSION_APPEND_TIME_OF_DAY=true
export OUT_DIR=/work/out
export BUILD_USERNAME=karat-builder
export BUILD_HOSTNAME=karat-build
jobs=${KARAT_BUILD_JOBS:-8}
[[ "$jobs" =~ ^[1-9][0-9]*$ ]]

patch=/work/port/patches/frameworks_base-tv-compat-metadata.patch
if git -C frameworks/base apply --reverse --check "$patch" 2>/dev/null; then
    : # This exact TV-only patch is already present.
else
    git -C frameworks/base apply --check "$patch"
    git -C frameworks/base apply "$patch"
fi

# Full checks are intentional: do not set ALLOW_MISSING_DEPENDENCIES or turn
# off VINTF/SELinux validation to conceal unresolved integration problems.
build/soong/soong_ui.bash --dumpvars-mode \
    --vars='TARGET_PRODUCT TARGET_ARCH TARGET_ARCH_VARIANT TARGET_CPU_VARIANT TARGET_USES_64_BIT_BINDER TARGET_DEVICE PRODUCT_SHIPPING_API_LEVEL PRODUCT_EXTRA_VNDK_VERSIONS PRODUCT_IS_ATV TARGET_COPY_OUT_PRODUCT TARGET_COPY_OUT_SYSTEM_EXT' \
    > /work/state/product-config.txt
build/soong/soong_ui.bash --make-mode -j"$jobs" systemimage
python3 /work/port/tools/check_candidate.py \
    /work/out/target/product/karat/system.img \
    --metadata /work/port/reports/stock-super.json \
    --output /work/state/candidate-size-check.json
