# Hardware findings and open work

## Working configuration

The demonstrated combination is LineageOS 20 userspace, the original Amazon
ARM64 kernel and an Android 11 / VNDK 30 vendor stack. Userspace is ARM32; the
kernel architecture does not imply that ARM64 APKs will run. The super partition
layout is retained, without resizing logical partitions.

The framework uses HDMI playback device type 4 and the existing MediaTek CEC
HAL. Advertising an audio-system device type is not an ARC/eARC fix.

## Corrections established during bring-up

1. The generic system image's system_ext property file overrode ADB authentication.
   The device configuration now supplies `ro.adb.secure=1` and enables Bluetooth
   HID host. The legacy vendor USB default required a separate MTP-to-ADB change
   for USB debugging during the private test.
2. Legacy vendor policy needed compatibility mappings and narrowly reviewed
   adjustments. The corrected IDME label also required restoring the
   `proc_idme_30_0_0` mapping. Normal init compilation and a separate strict
   neverallow audit were both used; no permissive SELinux mode was introduced.
3. The retained main audio XML selected an unavailable `custom_smp` engine and
   contained the unsupported `AUDIO_DEVICE_OUT_AVLS` output. The converter
   selects the default engine and removes only the four AVLS branch elements,
   checking the retained ports and HDMI PCM route. The separate generic
   Bluetooth legacy policy is left unchanged. A low internal media volume was
   an additional cause of quiet sound after the routing correction.
4. After external-power startup, CEC was enabled and the LG TV detected, but the
   stick was not the active source. One Touch Play restored remote navigation.
   The retained playback service requests it on screen wake but skips normal
   boot. The helper performs one request after BOOT_COMPLETED. A real restart
   verified the request, successful callback, source selection and subsequent
   physical LG arrows/OK without a manual HDMI command.

The CEC service's availability flag was false during an earlier period of
working input. Judge remote behavior using actual received commands and visible
response, not that flag alone. Startup One Touch Play can wake the TV and select
the stick's HDMI input. Standby/hotplug and other television models need testing.

## Limits of these results

The successful test is one development device, not a compatibility guarantee.
Basic media playback does not establish 4K hardware decoding, frame-rate
switching, every encoded-audio format, certified streaming DRM or ARC/eARC.
Back, held-key repeat and player transport controls also need separate tests.

Twelve generic kernel configuration exceptions remained with the original
kernel. Rebuilt-kernel candidates did not reach verified Android startup. This
release preserves those failures as open work instead of describing the port
as fully compatible with Android 13.

Raw lab records and backups remain private. This document summarizes the
hardware observations; the public repository cannot independently replay the
entire device trial without locally supplied firmware and hardware.
