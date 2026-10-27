"""Validate converted output before making the LiveContainer IPA."""
from pathlib import Path
import hashlib
import json
import plistlib
import shutil
import struct
import subprocess
import zipfile
import tempfile
from native_first_haptic import verify as verify_first_haptic
from native_guide import records as guide_records, chain as guide_chain


def zero_fill_sections(data):
    """Return section headers requiring offset=0 (Mach-O loader invariant).

    Zero-fill sections occupy virtual memory only. Normalizing the file-offset
    field does not move bytes or change addresses, sizes or TLS descriptors.
    Only little-endian, thin 64-bit Mach-O is accepted by this ARM64 pipeline.
    """
    if len(data) < 32 or data[:4] != b'\xcf\xfa\xed\xfe':
        raise ValueError('Expected a thin 64-bit Mach-O')
    ncmds, sizeofcmds = struct.unpack_from('<II', data, 16)
    end = 32 + sizeofcmds
    if end > len(data):
        raise ValueError('Truncated Mach-O load commands')
    pos = 32
    sections = []
    for _ in range(ncmds):
        if pos + 8 > end:
            raise ValueError('Truncated load command')
        cmd, size = struct.unpack_from('<II', data, pos)
        if size < 8 or size % 8 or pos + size > end:
            raise ValueError('Invalid load command size')
        if cmd == 0x19:  # LC_SEGMENT_64
            if size < 72:
                raise ValueError('Truncated segment command')
            count = struct.unpack_from('<I', data, pos + 64)[0]
            if 72 + count * 80 > size:
                raise ValueError('Truncated section headers')
            for i in range(count):
                sec = pos + 72 + i * 80
                flags = struct.unpack_from('<I', data, sec + 64)[0]
                if flags & 0xff in (0x1, 0xc, 0x12):
                    name = data[sec:sec+16].split(b'\0')[0].decode()
                    seg = data[sec+16:sec+32].split(b'\0')[0].decode()
                    offset = struct.unpack_from('<I', data, sec + 48)[0]
                    sections.append((seg + '/' + name, sec + 48, offset))
        pos += size
    if pos != end:
        raise ValueError('Load-command count/size mismatch')
    return sections


def normalize_zero_fill(path):
    data = bytearray(path.read_bytes())
    changes = []
    for name, field, old in zero_fill_sections(data):
        if old:
            struct.pack_into('<I', data, field, 0)
            changes.append({'section': name, 'old_offset': old, 'new_offset': 0})
    if changes:
        path.write_bytes(data)
    if any(offset for _, _, offset in zero_fill_sections(path.read_bytes())):
        raise ValueError(f'Invalid zero-fill offset remains: {path}')
    return changes


app = Path('build/SegaRally.app').resolve()
def run(*args):
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT)

def exports(path):
    return {x.strip() for x in run('xcrun', 'nm', '-gUj', str(path)).splitlines()
            if x.strip().startswith('_')}

p = app / 'Info.plist'
info = plistlib.loads(p.read_bytes())
info.update(CFBundleVersion='1027.13', Port0rBuildID='Release-20261027', CFBundleName='Sega Rally Championship', CFBundleDisplayName='Sega Rally Championship',
            CADisableMinimumFrameDurationOnPhone=True,
            UISupportedInterfaceOrientations=['UIInterfaceOrientationLandscapeLeft', 'UIInterfaceOrientationLandscapeRight'],
            UIFileSharingEnabled=True, LSSupportsOpeningDocumentsInPlace=True,
            GCSupportedGameControllers=[{'ProfileName': 'ExtendedGamepad'}],
            GCSupportsControllerUserInteraction=True)
info.pop('LSMinimumSystemVersion', None)
info.pop('SHIMTrace', None)
info['SHIMStats'] = False
info['MetalHudEnabled'] = False
# User-supplied square artwork. Preserve the complete logo and both cars.
icon = Path('assets/SegaRallyIcon.jpg').resolve()
master = Path('build/Port0r-icon.png').resolve()
run('sips', '-s', 'format', 'png', str(icon), '--out', str(master))
for name, pixels in [('AppIcon60x60@2x', 120), ('AppIcon60x60@3x', 180),
                     ('AppIcon76x76@2x', 152), ('AppIcon83.5x83.5@2x', 167)]:
    run('sips', '-z', str(pixels), str(pixels), str(master), '--out', str(app / (name + '.png')))
info['CFBundleIcons'] = {'CFBundlePrimaryIcon': {'CFBundleIconFiles': ['AppIcon60x60'],
                                               'UIPrerenderedIcon': True}}
info['CFBundleIcons~ipad'] = {'CFBundlePrimaryIcon': {
    'CFBundleIconFiles': ['AppIcon60x60', 'AppIcon76x76', 'AppIcon83.5x83.5'],
    'UIPrerenderedIcon': True}}
info['CFBundleIconFiles'] = ['AppIcon60x60']
p.write_bytes(plistlib.dumps(info))
(app / 'embedded.mobileprovision').unlink(missing_ok=True)
(app / 'AppIconMarketing.png').unlink(missing_ok=True)
main = app / info['CFBundleExecutable']
original_main = main.read_bytes()
verify_first_haptic(original_main, patched=True)
original_guide = guide_records(original_main)
original_chain = guide_chain(original_main, 0x5803a8)
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
          'icon': 'user supplied Sega Rally Championship artwork resized to iOS PNG sizes',
          'signing': 'ad-hoc only, no Apple identity/profile; LiveContainer must re-sign',
          'build': 'release without FPS/HUD, runtime counters, log capture, statistics or shader dumps',
          'compression': 'ZIP deflate level 9; symlinks preserved',
          'stripped_symbols': []}
for m in machos:
    before_bytes = m.stat().st_size
    before_exports = exports(m)
    zero_fill_fixes = normalize_zero_fill(m)
    run('xcrun', 'strip', '-S', '-x', str(m))
    zero_fill_fixes.extend(normalize_zero_fill(m))
    assert exports(m) == before_exports, m
    report['stripped_symbols'].append({'path': str(m.relative_to(app)),
        'before_bytes': before_bytes, 'after_bytes': m.stat().st_size,
        'exported_symbols_preserved': len(before_exports)})
    if m == main:
        verify_first_haptic(m.read_bytes(), patched=True)
        assert guide_records(m.read_bytes()) == original_guide
        assert guide_chain(m.read_bytes(), 0x5803a8) == original_chain
    assert run('lipo', '-archs', str(m)).strip() == 'arm64', m
    version = run('vtool', '-show-build', str(m))
    assert 'platform IOS' in version, (m, version)
    loads = run('otool', '-l', str(m))
    assert 'cryptid 1' not in loads, m
    deps = run('otool', '-L', str(m))
    assert '/System/Library/Frameworks/AppKit.framework/' not in deps, m
    report['macho'].append({'path': str(m.relative_to(app)), 'build_version': version,
                            'dependencies': deps, 'zero_fill_fixes': zero_fill_fixes})
    # Replace conversion entitlements, including placeholder team IDs, with a
    # plain ad-hoc signature. LiveContainer supplies its own signing context.
    run('codesign', '--force', '--sign', '-', str(m))
run('codesign', '--force', '--sign', '-', str(app))
run('codesign', '--verify', '--deep', '--strict', str(app))
for m in machos:
    run('codesign', '--verify', '--strict', str(m))
    assert all(offset == 0 for _, _, offset in zero_fill_sections(m.read_bytes())), m
payload = Path('build/Payload')
payload.mkdir(exist_ok=True)
shutil.copytree(app, payload / app.name, symlinks=True)
ipa = Path('build/SegaRally-LiveContainer-UNSIGNED.ipa')
subprocess.run(['zip', '-q', '-9', '-r', '-y', '-X', str(ipa.resolve()), 'Payload'],
               cwd=payload.parent, check=True)
with zipfile.ZipFile(ipa) as z:
    assert z.testzip() is None
    assert f'Payload/{app.name}/Info.plist' in z.namelist()
    assert not any(n.endswith('embedded.mobileprovision') for n in z.namelist())
with tempfile.TemporaryDirectory(prefix='segarally-ipa-verify-') as verify_dir:
    run('ditto', '-x', '-k', str(ipa.resolve()), verify_dir)
    unpacked = Path(verify_dir) / 'Payload' / app.name
    run('codesign', '--verify', '--deep', '--strict', str(unpacked))
    verify_first_haptic((unpacked / info['CFBundleExecutable']).read_bytes(), patched=True)
    packed_info = plistlib.loads((unpacked / 'Info.plist').read_bytes())
    assert packed_info['CADisableMinimumFrameDurationOnPhone'] is True
    assert packed_info['SHIMStats'] is False and packed_info['MetalHudEnabled'] is False
    forbidden = {'.log', '.dSYM', '.o', '.m', '.h'}
    assert not any(x.suffix in forbidden for x in unpacked.rglob('*'))
    assert not (unpacked / 'AppIconMarketing.png').exists()
report['ipa_bytes'] = ipa.stat().st_size
report['payload_bytes'] = sum(x.stat().st_size for x in app.rglob('*') if x.is_file() and not x.is_symlink())
report['ipa_sha256'] = hashlib.sha256(ipa.read_bytes()).hexdigest()
Path('build/validation.json').write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))
