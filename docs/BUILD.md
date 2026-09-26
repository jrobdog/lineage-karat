# Building and inspecting the source

This is a developer workflow for a system-image prototype, not a flashing guide.
The full OS was built on a Linux x86-64 host using the pinned Android toolchain.
Allow substantial disk space for the Android checkout and output. The original
successful system build used up to 24 jobs within a 56 GiB memory limit; tune
parallelism for your host. Python tools use Python 3.11 or newer.

## Pinned platform source

The [manifest](../manifests/karat-pinned.xml) pins upstream project revisions.
The publication removed an unused private remote declaration; no project revision
changed. Supply Git, Git LFS, the Android `repo` tool and the dependencies required
by the pinned LineageOS 20 build environment.

Two existing container entry points are retained. They expect these paths:

| Container path | Purpose |
| --- | --- |
| `/src` | Writable Android source checkout |
| `/work/port` | This repository |
| `/work/state` | Local sync/build metadata |
| `/work/out` | Local build output |

Run `build-support/sync.sh` in that environment. It initializes the pinned
LineageOS manifest, installs this repository's manifest and syncs the source.
Copy `device/amazon/karat` into `/src/device/amazon/karat` before building.
Then run `build-support/build-system.sh`, optionally setting `KARAT_BUILD_JOBS`.
The wrapper applies the TV-specific frameworks/base patch and builds only
`systemimage`. The output is not an OTA or a complete installation package.

The original generated system image was built before the source-level ADB/HID
property correction. The device configuration now contains that correction;
the public snapshot has not undergone another complete Android rebuild.
The corresponding offline correction was tested on the installed experimental
image. Do not claim byte-for-byte reproduction of that image from a new build.

## Local firmware and offline tools

No firmware inputs are provided. `reports/firmware-inputs.json` identifies the
original analysis baseline, while individual preparation scripts pin later
unlocked or corrected artifacts. These are different stages, not interchangeable
inputs. Some hashes are specific to the original test artifacts; the tools will
refuse other captures even if they come from the same model. Review any proposed
adaptation instead of removing the guards to force a pass.

`tools/extract_super.py` verifies metadata checksums and partition bounds before
extracting a locally supplied raw super image. `tools/check_candidate.py` checks
raw ext4 format and partition budget; a pass does not establish bootability or
hardware compatibility. The checked-in geometry is an anonymized reference,
not permission to apply it to an unknown device.

The `prepare_*` scripts perform offline image work only. They preserve originals,
require separate outputs and include hash/layout checks. The ramdisk preparation
is explicitly for an unlocked experiment and removes system/vendor dm-verity
mount flags. The image tools' development signing steps do not establish stock
boot-chain trust. Read [SECURITY.md](../SECURITY.md) before using them.

Vendor policy must be compiled against the actual platform inputs and inspected
for effective-access changes. Use `tools/check_installed_policy.py` for normal
init compilation plus the separate strict neverallow audit. Inspect both results:
that tool's process exit status follows the normal-init compilation result, so
a zero exit alone does not prove that the strict audit passed.

The final audio correction is exposed by `prepare_vendor_image.py
--lineage-audio-policy`; `--adb-usb-default` preserves the separately tested USB
default change. Firmware layout, provenance, policy compilation, file metadata,
AVB self-verification and complete output read-back still require validation.
No device-writing or factory-reset automation is included here.

## HDMI startup helper

See [the helper instructions](../apps/KaratCecStartup/README.md). It needs a
platform-signature permission and is intended for a matching custom OS build.
It is not a normal app that can be sideloaded onto stock Fire OS and expected to
control HDMI. This release includes source, not a pre-signed APK or signing key.

## Local checks

From the repository root:

```sh
python3 -m unittest discover -s tests -v
python3 tools/check_public_tree.py
```

The original image tests look for an excluded local `stock/reference-super.img`
and `stock/images/system.img`. Without those fixtures, two rejection tests run
and six firmware-dependent tests skip. Neither outcome certifies hardware.
The public-tree check enforces the source allowlist and basic privacy rules;
also run a dedicated secret scanner over both files and Git history before
publishing updates. Review generated output separately and keep it untracked.
