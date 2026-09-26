# SPDX-License-Identifier: Apache-2.0
PRODUCT_SUPPORTS_CAMERA := false
PRODUCT_SUPPORTS_TUNER := false
TARGET_ATV_FORCE_1080_SCALING := true

$(call inherit-product, device/google/atv/products/atv_base.mk)
$(call inherit-product, $(SRC_TARGET_DIR)/product/gsi_release.mk)
$(call inherit-product, vendor/lineage/config/common_mini_tv.mk)
$(call inherit-product, device/amazon/karat/device.mk)

PRODUCT_NAME := lineage_karat
PRODUCT_DEVICE := karat
PRODUCT_BRAND := Amazon
PRODUCT_MANUFACTURER := Amazon
PRODUCT_MODEL := Fire TV Stick 4K Max (2nd Gen) Experimental
PRODUCT_CHARACTERISTICS := tv
PRODUCT_SHIPPING_API_LEVEL := 30

# Keep only the legacy VNDK required by this stick to conserve super space.
PRODUCT_EXTRA_VNDK_VERSIONS := 30
PRODUCT_INSTALL_EXTRA_FLATTENED_APEXES := false

# The only device image currently supported by the build script is system.img.
# No installer/OTA is provided: Fire OS policy and AVB integration are open.
PRODUCT_BUILD_BOOT_IMAGE := false
PRODUCT_BUILD_RECOVERY_IMAGE := false
PRODUCT_BUILD_VENDOR_BOOT_IMAGE := false
PRODUCT_BUILD_VENDOR_IMAGE := false
PRODUCT_BUILD_PRODUCT_IMAGE := false
PRODUCT_BUILD_SYSTEM_EXT_IMAGE := false
PRODUCT_BUILD_VBMETA_IMAGE := false
PRODUCT_BUILD_SUPER_PARTITION := false
PRODUCT_BUILD_SUPER_EMPTY_IMAGE := false
PRODUCT_BUILD_USERDATA_IMAGE := false
PRODUCT_BUILD_CACHE_IMAGE := false
