#!/usr/bin/env python3
"""Build the experimental helper with pinned Android 13 tools and the builder's key."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import zipfile

SDK_SHA = 'a71eb5eea6dfa4152a64e80f6afa3cd2fdd9b09bb533501b09ed8bfe1b1000ff'
R8_SHA = 'ebaa6b702d746cb0bd2db28b2be220979c70ad7a4031848f09a28e7057b75d18'


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def run(args):
    return subprocess.run(list(map(str, args)), capture_output=True, check=True).stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('android-jar', 'r8-jar', 'platform-key', 'platform-cert', 'out'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--expected-platform-cert-sha256', required=True,
                        help='SHA-256 of the platform signing certificate for your own OS build')
    args = parser.parse_args()
    cert_sha = args.expected_platform_cert_sha256.lower()
    if not re.fullmatch(r'[0-9a-f]{64}', cert_sha):
        raise ValueError('Require a 64-character SHA-256 certificate fingerprint')
    if digest(args.android_jar) != SDK_SHA or digest(args.r8_jar) != R8_SHA:
        raise ValueError('Require the pinned Android 13 build inputs')
    cert = run(['openssl', 'x509', '-in', args.platform_cert, '-outform', 'DER'])
    if hashlib.sha256(cert).hexdigest() != cert_sha:
        raise ValueError('Certificate does not match the explicitly expected platform signer')
    source = Path(__file__).resolve().parent
    args.out.mkdir(parents=True, mode=0o700, exist_ok=False)
    classes, dex = args.out / 'classes', args.out / 'dex'
    classes.mkdir()
    dex.mkdir()
    run(['javac', '--release', '8', '-classpath', args.android_jar, '-d', classes,
         *sorted((source / 'src').rglob('*.java'))])
    class_jar = args.out / 'classes.jar'
    with zipfile.ZipFile(class_jar, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(classes.rglob('*.class')):
            archive.write(path, path.relative_to(classes).as_posix())
    run(['java', '-cp', args.r8_jar, 'com.android.tools.r8.D8', '--release',
         '--min-api', '33', '--lib', args.android_jar, '--output', dex, class_jar])
    unsigned = args.out / 'unsigned.apk'
    run(['aapt', 'package', '-f', '-M', source / 'AndroidManifest.xml',
         '-I', args.android_jar, '-F', unsigned])
    with zipfile.ZipFile(unsigned, 'a', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(dex / 'classes.dex', 'classes.dex')
    apk = args.out / 'karat-cec-startup.apk'
    run(['apksigner', 'sign', '--key', args.platform_key, '--cert', args.platform_cert,
         '--min-sdk-version', '33', '--v1-signing-enabled', 'false', '--out', apk, unsigned])
    verified = run(['apksigner', 'verify', '--print-certs', apk]).decode()
    if 'certificate SHA-256 digest: ' + cert_sha not in verified:
        raise ValueError('Unexpected APK signer')
    manifest = run(['aapt', 'dump', 'badging', apk]).decode()
    (args.out / 'badging.txt').write_text(manifest)
    report = {'apk': str(apk.resolve()), 'sha256': digest(apk),
              'bytes': apk.stat().st_size, 'platform_signer_sha256': cert_sha,
              'permissions': ['android.permission.RECEIVE_BOOT_COMPLETED',
                              'android.permission.HDMI_CEC'],
              'experimental_system_component': True, 'signature_verified': True}
    (args.out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
