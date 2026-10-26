"""Repackage the exact validated IPA with the two texture-fence defaults.

No SDK compilation is needed for these two MOV-immediate changes. Refresh the
existing ad-hoc CodeDirectory page hashes; refuse real CMS signatures. The
baseline was built, codesign-verified and tested by run 40317867463. Every other
payload file must remain byte-identical. LiveContainer still re-signs the IPA.
"""
from pathlib import Path
import copy
import argparse
import hashlib
import io
import json
import plistlib
import struct
import zipfile
from native_texture_sync import SITES

BASE_IPA_SHA256 = 'b8aab5643091218bb60d8c9c2378cda7f7501422e85d4b160943b656928d6ed2'
MAIN = 'Payload/SegaRally.app/port0r'
arguments = argparse.ArgumentParser()
arguments.add_argument('--original-rendering', action='store_true', help='Stable package: preserve all original renderer defaults')
stable = arguments.parse_args().original_rendering


def directories(data):
    if data[:4] != b'\xcf\xfa\xed\xfe' or struct.unpack_from('<I',data,4)[0] != 0x100000c:
        raise ValueError('Expected thin ARM64 main executable')
    pos = 32
    signature = None
    for _ in range(struct.unpack_from('<I',data,16)[0]):
        command, size = struct.unpack_from('<II',data,pos)
        if command == 0x1d: signature = struct.unpack_from('<II',data,pos+8)
        pos += size
    if not signature: raise ValueError('Missing baseline ad-hoc signature')
    offset, size = signature
    magic, length, count = struct.unpack_from('>III',data,offset)
    if magic != 0xfade0cc0 or length > size or offset+size > len(data):
        raise ValueError('Invalid signature SuperBlob')
    result = []
    for i in range(count):
        kind, relative = struct.unpack_from('>II',data,offset+12+i*8)
        start = offset+relative
        magic, length = struct.unpack_from('>II',data,start)
        if start+length > offset+size: raise ValueError('Signature blob out of bounds')
        if kind == 0x10000 and length > 8:
            raise ValueError('Refusing to modify an identity-signed CMS signature')
        if magic != 0xfade0c02: continue
        version, flags, hashes, identity, special, pages, limit = struct.unpack_from('>7I',data,start+8)
        hash_size, hash_type, platform, shift = data[start+36:start+40]
        if not flags & 2: raise ValueError('Only existing ad-hoc signatures supported')
        if version >= 0x20300 and limit == 0xffffffff:
            limit = struct.unpack_from('>Q',data,start+56)[0]
        algorithm = {1:'sha1',2:'sha256',3:'sha256',4:'sha384'}.get(hash_type)
        if not algorithm or hash_size not in (20,32,48) or shift > 20 or not shift:
            raise ValueError('Unsupported CodeDirectory hash parameters')
        page_size = 1 << shift
        if limit != offset or pages != (limit+page_size-1)//page_size:
            raise ValueError('Unexpected CodeDirectory code extent')
        if hashes+pages*hash_size > length:
            raise ValueError('CodeDirectory slots out of bounds')
        result.append((start+hashes,pages,limit,page_size,hash_size,algorithm))
    if not result: raise ValueError('No CodeDirectory found')
    return result


def check_pages(data):
    checked = 0
    for hashes,pages,limit,page_size,hash_size,algorithm in directories(data):
        for page in range(pages):
            digest = hashlib.new(algorithm,data[page*page_size:min(limit,(page+1)*page_size)]).digest()[:hash_size]
            if data[hashes+page*hash_size:hashes+(page+1)*hash_size] != digest:
                raise ValueError(f'Invalid code-page signature at page {page}')
            checked += 1
    return checked


sources = list(Path('base').glob('*.ipa'))
if len(sources) != 1: raise SystemExit('Expected one baseline IPA')
baseline = sources[0].read_bytes()
if hashlib.sha256(baseline).hexdigest() != BASE_IPA_SHA256:
    raise SystemExit('Validated baseline IPA hash mismatch')
with zipfile.ZipFile(io.BytesIO(baseline)) as original:
    assert original.testzip() is None
    before = original.read(MAIN)
    original_pages = check_pages(before)
    after = bytearray(before)
    for offset,key,_ in SITES:
        if struct.unpack_from('<I',before,offset)[0] != 0x52800001:
            raise ValueError(f'Unexpected default for {key}')
        if struct.unpack_from('<I',before,offset+8)[0] != 0x34000060:
            raise ValueError(f'Unexpected existing wait guard for {key}')
        if not stable: struct.pack_into('<I',after,offset,0x52800021)
    hash_ranges = []
    for hashes,pages,limit,page_size,hash_size,algorithm in directories(before):
        for page in range(pages):
            start,end = page*page_size,min(limit,(page+1)*page_size)
            if after[start:end] == before[start:end]: continue
            pos = hashes+page*hash_size
            after[pos:pos+hash_size] = hashlib.new(algorithm,after[start:end]).digest()[:hash_size]
            hash_ranges.append((pos,pos+hash_size))
    assert check_pages(after) == original_pages
    permitted = [(offset,offset+4) for offset,_,_ in SITES]+hash_ranges
    assert all(any(start<=i<end for start,end in permitted)
               for i,(old,new) in enumerate(zip(before,after)) if old!=new)
    seal = plistlib.loads(original.read('Payload/SegaRally.app/_CodeSignature/CodeResources'))
    assert all('port0r' not in seal.get(kind,{}) for kind in ('files','files2'))
    build = Path('build'); build.mkdir(exist_ok=True)
    output = build/('SegaRally-LiveContainer-STABLE-UNSIGNED.ipa' if stable else 'SegaRally-LiveContainer-texture-sync-UNSIGNED.ipa')
    with zipfile.ZipFile(output,'w') as target:
        target.comment = original.comment
        for entry in original.infolist():
            target.writestr(copy.copy(entry),after if entry.filename==MAIN else original.read(entry.filename))
    with zipfile.ZipFile(output) as target:
        assert target.testzip() is None
        assert original.namelist() == target.namelist()
        assert check_pages(target.read(MAIN)) == original_pages
        for entry in original.namelist():
            if stable or entry != MAIN: assert original.read(entry)==target.read(entry),entry
        assert not any(name.lower().endswith(('.zip','.rom','.chd','.pck')) for name in target.namelist())
report = {'baseline_run':40317867463,'baseline_ipa_sha256':BASE_IPA_SHA256,
          'ipa_sha256':hashlib.sha256(output.read_bytes()).hexdigest(),
          'changed_default_instructions':0 if stable else 2,'texture_wait_defaults':{key:0 if stable else 1 for _,key,_ in SITES},
          'validated_signature_pages':original_pages,'updated_signature_page_hashes':len(hash_ranges),
          'other_payload_files':'byte-identical to validated baseline',
          'all_payload_files_byte_identical':stable,
          'build_method':'stable original-rendering package from pinned validated SDK build' if stable else 'binary comparison package on Linux; original full SDK build is the pinned baseline',
          'signing':'existing ad-hoc signatures preserved; no Apple identity; LiveContainer re-signs' if stable else 'existing ad-hoc CodeDirectory hashes refreshed; no Apple identity; LiveContainer re-signs',
          'device_rendering_verified':False,'flicker_fixed':False}
(build/'texture-comparison-validation.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
print('PASS: original renderer defaults and all payload files preserved; code-page hashes, resources, ZIP integrity and no ROM archives verified' if stable else
      'PASS: exact baseline, two native defaults, all code-page hashes, unchanged resources, ZIP integrity and no ROM archives')
