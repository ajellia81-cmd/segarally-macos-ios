"""Validate converted output before making the LiveContainer IPA."""
from pathlib import Path
import hashlib
import json
import plistlib
import shutil
import subprocess
import zipfile

app = Path('build/SegaRally.app').resolve()
def run(*args):
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT)

p = app / 'Info.plist'
info = plistlib.loads(p.read_bytes())
info.update(CFBundleName='Port0r Rally', CFBundleDisplayName='Port0r Rally',
            CADisableMinimumFrameDurationOnPhone=True,
            UISupportedInterfaceOrientations=['UIInterfaceOrientationLandscapeLeft', 'UIInterfaceOrientationLandscapeRight'],
            UIFileSharingEnabled=True, LSSupportsOpeningDocumentsInPlace=True,
            GCSupportedGameControllers=[{'ProfileName': 'ExtendedGamepad'}],
            GCSupportsControllerUserInteraction=True)
info.pop('LSMinimumSystemVersion', None)
p.write_bytes(plistlib.dumps(info))
(app / 'embedded.mobileprovision').unlink(missing_ok=True)
machos = []
for p in app.rglob('*'):
    if not p.is_file() or p.is_symlink():
        continue
    if p.suffix.lower() in {'.zip', '.7z', '.chd', '.rom', '.bin', '.pck'}:
        raise SystemExit(f'Forbidden game/archive data: {p}')
    if p.read_bytes()[:4] == b'\xcf\xfa\xed\xfe':
        machos.append(p)
assert machos and (app / info['CFBundleExecutable']) in machos
report = {'device_launch_verified': False, 'original_resolution_percentages': 'unchanged',
          'native_resolution': 'runtime UIScreen.nativeBounds; no guessed iPhone dimensions',
          'refresh_rate': 'runtime maximumFramesPerSecond; 120 Hz capability only',
          'macho': [], 'removed_game_assets': 'Resources/srallyc cockpit packs',
          'signing': 'ad-hoc only, no Apple identity/profile; LiveContainer must re-sign'}
for m in machos:
    assert run('lipo', '-archs', str(m)).strip() == 'arm64', m
    version = run('vtool', '-show-build', str(m))
    assert 'platform IOS' in version, (m, version)
    loads = run('otool', '-l', str(m))
    assert 'cryptid 1' not in loads, m
    deps = run('otool', '-L', str(m))
    assert '/System/Library/Frameworks/AppKit.framework/' not in deps, m
    report['macho'].append({'path': str(m.relative_to(app)), 'build_version': version, 'dependencies': deps})
    # Replace conversion entitlements, including placeholder team IDs, with a
    # plain ad-hoc signature. LiveContainer supplies its own signing context.
    run('codesign', '--force', '--sign', '-', str(m))
run('codesign', '--force', '--sign', '-', str(app))
run('codesign', '--verify', '--deep', '--strict', str(app))
for m in machos:
    run('codesign', '--verify', '--strict', str(m))
payload = Path('build/Payload')
payload.mkdir(exist_ok=True)
shutil.copytree(app, payload / app.name, symlinks=True)
ipa = Path('build/SegaRally-LiveContainer-UNSIGNED.ipa')
run('ditto', '-c', '-k', '--keepParent', str(payload), str(ipa))
with zipfile.ZipFile(ipa) as z:
    assert z.testzip() is None
    assert f'Payload/{app.name}/Info.plist' in z.namelist()
    assert not any(n.endswith('embedded.mobileprovision') for n in z.namelist())
report['ipa_sha256'] = hashlib.sha256(ipa.read_bytes()).hexdigest()
Path('build/validation.json').write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))
