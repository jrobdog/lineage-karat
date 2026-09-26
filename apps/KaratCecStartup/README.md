# HDMI startup helper

On the tested LineageOS 20 playback framework, One Touch Play is requested when
waking the screen but not during normal boot. The LG TV detected the stick after
a power change, yet remote input did not resume until the stick announced itself
as the active source. One Touch Play restored control.

This helper requests that action once after `BOOT_COMPLETED`. It waits 1.5 seconds
for startup to settle, calls the HDMI playback client, waits at most 25 seconds
for the result and finishes the receiver. There is no periodic announcement or
retry after an unknown outcome. The request can wake the TV and select the
stick's HDMI input.

Version 1.0 was installed on the development device. A real restart produced one
boot request, a successful callback and active-source selection without a manual
command. The owner confirmed physical LG arrows and OK worked, corroborated by
received navigation/select CEC messages. Other TVs and power sequences have not
been accepted by that single test.

## Permissions and signing

The package requests only `RECEIVE_BOOT_COMPLETED` and `HDMI_CEC`. It has no network
permission, root daemon, launcher entry or shared system UID. Both exported
components require `HDMI_CEC`.

`HDMI_CEC` is a signature/privileged permission. Sign with the platform key for
your own custom OS, and independently verify the expected platform certificate
fingerprint. A normal third-party signing key does not grant this permission.
Do not reuse public Android test keys for a distributed OS; see the repository's
[security notes](../../SECURITY.md).

## Build

The build requires Java, OpenSSL, `aapt`, `apksigner`, and these pinned inputs
from the Android source checkout:

| Input | Revision | SHA-256 |
| --- | --- | --- |
| `prebuilts/sdk/33/system/android.jar` | `fcd7b576822ae46dbd3b0ed169f8a802850d5957` | `a71eb5eea6dfa4152a64e80f6afa3cd2fdd9b09bb533501b09ed8bfe1b1000ff` |
| `prebuilts/r8/r8.jar` | `80cd33e021c42be09eaa97f0563dd70673a20450` | `ebaa6b702d746cb0bd2db28b2be220979c70ad7a4031848f09a28e7057b75d18` |

Pass these explicit arguments to `build.py`:

```text
--android-jar PATH
--r8-jar PATH
--platform-key PRIVATE_KEY_PATH
--platform-cert CERTIFICATE_PATH
--expected-platform-cert-sha256 EXPECTED_CERTIFICATE_FINGERPRINT
--out NEW_OUTPUT_DIRECTORY
```

Keep all key material and generated APKs outside this source repository. The
certificate fingerprint is not a secret. The builder checks the SDK/R8 hashes,
certificate fingerprint and final APK signature.

## Activation and verification

Use an explicit ADB device selector and verify the device identity before
installation. After installing, launch
`org.lineageos.karat.cecstartup/.EnableActivity` once. This no-display activity
clears Android's newly installed/stopped package state and sends one explicit
test request. Verify both permissions are granted and the package is not stopped.

Restart and inspect only this helper's log tag (`KaratCecStartup`) plus the HDMI
service state. Expected messages are `Received android.intent.action.BOOT_COMPLETED`,
one startup request, and `One Touch Play result=0`. Confirm the physical remote
works without a manual HDMI action. A successful install alone is not a boot test.
Avoid broad app logs, which can contain account tokens.

Uninstalling `org.lineageos.karat.cecstartup` removes this startup behavior without
changing firmware or other app data.

[Pinned framework playback source](https://github.com/LineageOS/android_frameworks_base/blob/20301873c477fc51982c0b4b4aa02735caf0c4a5/services/core/java/com/android/server/hdmi/HdmiCecLocalDevicePlayback.java).
