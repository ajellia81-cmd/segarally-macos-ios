"""Verify the pinned native race telemetry ABI without executing ARM64 on Intel."""
from pathlib import Path
import hashlib
import json
import re
import struct

getter = bytes.fromhex('881601b008c12e91090140b9090000b9090540b9090400b9090940b9090800b9090d40b9090c00b9091140b9091000b9081540b9081400b9c0035fd6')
producer = {
    # state == 3, sub == 7 and phase == 5/7 form the live-race predicate;
    # debug.tcvr.rally_anyState is the explicit upstream override.
    0xd460: bytes.fromhex('1f0f0071200b477a487b1e120009457afb179f1ae85b00b96100005437008052'),
    # Remaining-time range plus that predicate publish first float as 0 or 1.
    0xdb6c: bytes.fromhex('08050051e99391521f01096be8279f1afa3340f908011a6a68620239689e00bd78a200b914f0a752561601b0d6c22e9188129f1ac8fe9f880801261ec8420099'),
}
header = Path('compatibility/shim/overrides/Port0rRaceABI.h').read_text()
array = header.split('Port0rRaceGetterCode[] = {', 1)[1].split('}', 1)[0]
assert bytes(int(x,16) for x in re.findall(r'0x([0-9a-fA-F]{2})',array)) == getter
report = []
for path in [
    Path('extracted/Port0r Rally.app/Contents/Frameworks/libtcvr_mame.dylib'),
    Path('build/SegaRally.app/Mac/Contents/Frameworks/libtcvr_mame.dylib'),
]:
    data = path.read_bytes()
    assert data[:4] == b'\xcf\xfa\xed\xfe'
    pos, segments, symtab = 32, [], None
    for _ in range(struct.unpack_from('<I',data,16)[0]):
        command, size = struct.unpack_from('<II',data,pos)
        if command == 0x19:
            segments.append(struct.unpack_from('<QQQQ',data,pos+24))
        if command == 2:
            symtab = struct.unpack_from('<IIII',data,pos+8)
        pos += size
    def at(address,length):
        for virtual,vsize,offset,fsize in segments:
            if virtual <= address and address + length <= virtual + fsize:
                return data[offset+address-virtual:offset+address-virtual+length]
        raise AssertionError(hex(address))
    assert symtab
    offset,count,strings,_ = symtab
    matches = []
    for i in range(count):
        index,kind,section,desc,value = struct.unpack_from('<IBBHQ',data,offset+i*16)
        if not index: continue
        name = data[strings+index:data.index(b'\0',strings+index)]
        if name == b'_tcvr_mame_rally_telemetry' and kind & 1 and kind & 14:
            matches.append(value)
    assert matches == [0x51b0], matches
    assert at(0x51b0,len(getter)) == getter
    for address,expected in producer.items(): assert at(address,len(expected)) == expected, hex(address)
    report.append({'path': str(path), 'getter_rva': '0x51b0', 'buffer_floats': 6,
        'getter_sha256': hashlib.sha256(getter).hexdigest(), 'producer_predicate_verified': True})
Path('build/race-state-validation.json').write_text(json.dumps(report,indent=2))
print('PASS: original and converted MAME getter copy exactly six floats; live-race producer predicate and runtime byte guard match pinned binary')
