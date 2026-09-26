# TV-specific source patch

`frameworks_base-tv-compat-metadata.patch` removes the framework build dependency
on TeleService compatibility metadata. This dedicated TV product does not
install TeleService. The pinned Telephony source called an API missing from the
pinned Android 13 framework, which blocked generation of that metadata.

The patch does not alter TeleService permissions or bypass global dependency
checks. It removes one build-list entry. Do not apply it to a phone product;
verify that TeleService remains absent from the final installed-file list.

The container build wrapper applies the patch idempotently to frameworks/base.
The source manifest and patch together describe the platform source baseline.

Upstream framework revision: `20301873c477fc51982c0b4b4aa02735caf0c4a5`.
[Related upstream Telephony change](https://review.lineageos.org/c/LineageOS/android_packages_services_Telephony/+/498035).
