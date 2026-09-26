# Security and release limitations

This project is an experimental port for an already-unlocked development device.
It is not a supported or hardened operating-system release.

The tested image used public Android development signing keys. Public keys of
this kind have publicly available private counterparts and cannot establish
exclusive publisher identity. AOSP explains why publicly released images need
privately held release keys in [Sign builds for release](https://source.android.com/docs/core/ota/sign_builds).
No keys or prebuilt images are distributed here. The standalone HDMI helper
build requires an explicitly supplied platform certificate fingerprint and key.
Do not sign a public ROM with the development fixtures used for the lab test.

The first-stage mount preparation removes system/vendor dm-verity mount flags
for the unlocked experiment. A self-verified AVB footer does not make the result
trusted by the stock Amazon boot chain. The retained GSI compatibility defaults
also disable rescue and privileged-permission allowlist enforcement. These are
visible in the source and remain release blockers; SELinux enforcing alone does
not make the complete system secure.

The original kernel and proprietary vendor drivers retain compatibility and
maintenance limitations. A displayed Android security-patch date is not proof
that all vendor/kernel vulnerabilities are addressed. Full VINTF, hardware,
DRM and long-term stability acceptance remains incomplete.

ADB authentication is enabled in the device configuration. No network ADB port
is enabled by this repository. If you enable legacy TCP ADB for development, it
requires authentication but does not provide TLS transport encryption; use a
trusted network and disable it when no longer needed. Never distribute an image
containing somebody else's authorized ADB key.

Public bug reports should contain redacted, minimal reproduction details.
Raw logs, firmware dumps and app configuration can contain device identifiers
or account tokens. For a vulnerability involving private data or a practical
security exploit, use GitHub's private vulnerability reporting for this repository
when available instead of opening a public issue.
