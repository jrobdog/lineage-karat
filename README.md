# Experimental LineageOS TV for Fire TV Stick 4K Max (karat)

An unofficial LineageOS 20 / Android 13 porting project for the **Fire TV Stick
4K Max, second generation (2023), AFTKRT / karat / MT8696T**. It combines ARM32
Android userspace and a 64-bit Binder interface with the device's original
ARM64 kernel and locally supplied vendor drivers.

**This is a source and research release, not an installable ROM release.** It
has booted on one already-unlocked development device. It is not an official
LineageOS build, a Google TV product, or a certified Android TV implementation.
Other Fire TV models and generations are outside its scope.

## Observed on the development device

The September 26, 2026 hardware session established the following limited results:

| Feature | Result |
| --- | --- |
| Android startup and TV launcher | Complete boot, encrypted data, SELinux enforcing |
| HDMI picture | Owner-confirmed picture and media playback |
| HDMI audio | Audio-policy compatibility correction restored LG internal-speaker output; source volume and corrected policy survived restarts |
| LG HDMI-CEC navigation | Arrows and OK accepted; automatic startup announcement tested through a restart and owner-confirmed remote control |
| Wi-Fi and authenticated ADB | Reconnection observed after restarts; legacy network ADB was enabled separately for the private test |
| Bluetooth remote profile | HID host enabled; Bluetooth remote pairing not tested |
| 4K decoding, DRM, codec coverage, ARC/eARC | Not established by the basic picture/audio test |
| TV standby, HDMI hotplug, held-key repeat | Further acceptance testing required |

The retained stock kernel does not meet all Android 13 kernel/VINTF requirements.
A separately rebuilt kernel did not reach a verified boot. The successful port
uses the original kernel; these compatibility gaps remain open.

## Contents

- [Device configuration](device/amazon/karat/) and the [pinned source manifest](manifests/karat-pinned.xml).
- [Offline tools](tools/) for partition validation, policy inspection and narrowly guarded image preparation.
- [HDMI startup helper](apps/KaratCecStartup/README.md), which requests One Touch Play once after boot.
- [Build notes](docs/BUILD.md), [hardware findings](docs/FINDINGS.md) and [validation status](reports/validation.json).

Firmware dumps, proprietary drivers, user data, device identities, credentials,
ADB keys, signing keys, raw device logs, APKs and compiled images are not part of
this repository. Obtain any necessary firmware inputs from a device you are
authorized to work on, and keep them outside version control. The preparation
tools deliberately reject artifacts that do not match their documented input
hashes. Changing a hash guard is not evidence that another build is compatible.

## Before building

Read [the build notes](docs/BUILD.md) and [security limitations](SECURITY.md).
The published source supports inspection and further development; it does not
provide an unlock exploit, flashing script, recovery image or general installer.
The original installation required a verified recovery path, a full backup and
a clean data reset. No installation should be inferred from a successful build.

For the source-only checks, use Python 3.11 or newer:

```sh
python3 -m unittest discover -s tests -v
python3 tools/check_public_tree.py
```

Two image-format rejection tests run without firmware. Six additional original
image tests are skipped unless the local, excluded firmware fixtures exist.
The public-tree check rejects unexpected binaries, identifying data, keys and
unapproved source files before publication.

## License and attribution

Original code and configuration are provided under [Apache-2.0](LICENSE).
[NOTICE](NOTICE) identifies the included AOSP tool and upstream dependencies.
Upstream projects retain their own licenses; this repository does not grant
redistribution rights to proprietary firmware or third-party applications.
Amazon, Fire TV, Android, Google TV and LineageOS names identify compatibility
or upstream projects and do not imply endorsement.
