# SPDX-License-Identifier: Apache-2.0
# The stock /vendor supplies MediaTek HDMI-CEC 1.0, graphics, audio, Wi-Fi,
# Bluetooth and OP-TEE/keymaster HALs. Do not install duplicate HAL servers.
PRODUCT_SYSTEM_PROPERTIES += \
    ro.hdmi.device_type=4 \
    ro.sf.lcd_density=320

# Enable the Android HDMI control service for a playback source. ARC/eARC is
# negotiated between the TV and audio system; this stick remains device type 4.
PRODUCT_COPY_FILES += \
    frameworks/native/data/etc/android.hardware.hdmi.cec.xml:$(TARGET_COPY_OUT_SYSTEM)/etc/permissions/android.hardware.hdmi.cec.xml

# Stock vendor supplies the device's Dalvik heap and hardware properties.
# This system-only target must not depend on generated vendor build.prop.

PRODUCT_SOONG_NAMESPACES += device/amazon/karat
PRODUCT_PACKAGES += \
    karat_plat_30.0.0.cil \
    karat_plat_30.0.0.compat.cil \
    karat_system_ext_30.0.0.compat.cil

# Optional headless bring-up: only the enrolled host's public ADB key belongs
# here. This ignored file is copied to /adb_keys by the standard Android build.
# Lineage userdebug keeps ro.adb.secure=1; do not use WITH_ADB_INSECURE.
ifneq ($(wildcard device/amazon/karat/prebuilts/adb_keys),)
ifneq ($(TARGET_BUILD_VARIANT),userdebug)
$(error The private headless karat build requires userdebug)
endif
ifdef WITH_ADB_INSECURE
$(error Headless karat requires authenticated ADB)
endif
PRODUCT_ADB_KEYS := device/amazon/karat/prebuilts/adb_keys
PRODUCT_SYSTEM_DEFAULT_PROPERTIES += persist.sys.usb.config=adb
endif
