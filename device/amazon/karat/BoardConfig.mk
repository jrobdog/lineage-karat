# SPDX-License-Identifier: Apache-2.0
# Phase 1: system-only TV prototype using the installed stock boot/vendor.
# Hardware values are from RS8182.3811N, not another Fire TV device tree.
TARGET_ARCH := arm
TARGET_ARCH_VARIANT := armv8-2a
TARGET_CPU_VARIANT := cortex-a55
TARGET_CPU_VARIANT_RUNTIME := cortex-a55
TARGET_CPU_ABI := armeabi-v7a
TARGET_CPU_ABI2 := armeabi
TARGET_USES_64_BIT_BINDER := true
TARGET_BOARD_PLATFORM := mt8696
TARGET_BOOTLOADER_BOARD_NAME := mt8696

include build/make/target/board/BoardConfigGsiCommon.mk

# GSI's system_ext property file overrides system ro.adb.secure=1 with 0.
# Retain its compatibility settings with authenticated ADB for this private TV.
TARGET_SYSTEM_EXT_PROP := device/amazon/karat/system_ext.prop

# The kernel is arm64; Android userspace is arm32. This product deliberately
# builds no boot, recovery, vendor or firmware images. Stock blobs stay local.
TARGET_KERNEL_ARCH := arm64
TARGET_NO_KERNEL := true
TARGET_NO_RECOVERY := true

# Replace the generic GSI geometry with the actual karat super geometry.
# tools/check_candidate.py also enforces the space left by stock vendor/product.
BOARD_SUPER_PARTITION_SIZE := 1625292800
BOARD_SUPER_PARTITION_GROUPS := main
BOARD_MAIN_SIZE := 1623195648
BOARD_MAIN_PARTITION_LIST := system vendor product
BOARD_SYSTEMIMAGE_PARTITION_RESERVED_SIZE := 33554432
BOARD_CACHEIMAGE_PARTITION_SIZE := 536870912

# New platform code uses current VNDK; the product includes the v30 snapshot
# required by the retained Android 11 vendor. Do not change this to v30.
BOARD_VNDK_VERSION := current

# Recognize the exact optional Amazon/MediaTek/Dolby extensions retained in vendor.
# This does not relax the platform's standard HAL or kernel requirements.
DEVICE_FRAMEWORK_COMPATIBILITY_MATRIX_FILE += device/amazon/karat/compatibility_matrix.xml
