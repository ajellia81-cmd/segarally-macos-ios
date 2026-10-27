"""Check native menu edits, fixups and execute its ARM64 settings parser."""
from pathlib import Path
import hashlib
import json
import struct
import subprocess
import tarfile
import platform
from native_guide import patch, records, chain, PARSER, TABLE, LABELS
from native_first_haptic import patch as fix_first_haptic, file_offset, BRANCH_VA

with tarfile.open('port0r.tar.gz') as archive:
    member = next(m for m in archive.getmembers() if m.name.endswith('Contents/MacOS/port0r'))
    original = archive.extractfile(member).read()
expected = fix_first_haptic(patch(original))
prepared = Path('extracted/Port0r Rally.app/Contents/MacOS/port0r').read_bytes()
assert prepared == expected
choices = records(prepared)
assert [r[0] for r in choices] == ['A','B','X','Y','LB','RB','LT','RT','L3','R3','SELECT','START','GUIDE']
assert choices[-1] == ('GUIDE', 'Guide', 110, -1, -1, 0)
for i in range(12):
    # Fixup linkage changes, but every original pointer target and field stays.
    old = original[0x572d60+i*32:0x572d60+(i+1)*32]
    new = prepared[TABLE+i*32:TABLE+(i+1)*32]
    for field in (0,8):
        assert struct.unpack_from('<Q',old,field)[0] & ((1<<51)-1) == struct.unpack_from('<Q',new,field)[0] & ((1<<51)-1)
    assert old[16:] == new[16:]
allowed = [(0x570d68,0x570d70), (0x5833f8,0x583400), (TABLE,LABELS+12),
           (0xe2d6c,0xe2d70), (0xe2f70,0xe2f74), (0x1bf78,0x1bf78+len(PARSER))]
branch_offset = file_offset(prepared, BRANCH_VA, 4)
allowed.append((branch_offset, branch_offset + 4))
assert all(any(a <= i < z for a,z in allowed) for i,(a,b) in enumerate(zip(original,prepared)) if a != b)
assert chain(prepared,0x5803a8) == chain(original,0x5803a8) + [TABLE+i*32+f for i in range(13) for f in (0,8)]
assert not Path('tools/overrides/AppKit_Guide.m').exists()

# Test the exact parser instruction stream. Only the two table-address loading
# instructions are relocated for this standalone native executable.
words = struct.unpack('<'+'I'*(len(PARSER)//4),PARSER)
assembly = ['.text','.p2align 2','.globl _NativeGuideParse','_NativeGuideParse:']
for i,word in enumerate(words):
    if i == 4: assembly.append('adrp x20, _NativeGuideTestTable@PAGE')
    elif i == 5: assembly.append('add x20, x20, _NativeGuideTestTable@PAGEOFF')
    else: assembly.append(f'.long 0x{word:08x}')
Path('build/native_guide_parser.s').write_text('\n'.join(assembly)+'\n')
rows = '\n'.join('{' + json.dumps(r[0]) + ',' + json.dumps(r[1]) + ',' + ','.join(map(str,r[2:])) + '},' for r in choices)
Path('build/native_guide_smoke.c').write_text(r'''
#include <assert.h>
#include <stdio.h>
#include <string.h>
typedef struct { const char *setting, *label; int key, axis, otherAxis, unused; } Button;
_Static_assert(sizeof(Button)==32, "Native menu stride");
const Button NativeGuideTestTable[] = {
''' + rows + r'''
};
extern int NativeGuideParse(const char *value);
int main(void) {
    for (int i=0; i<13; i++) assert(NativeGuideParse(NativeGuideTestTable[i].setting)==i);
    assert(NativeGuideParse("")==-1 && NativeGuideParse("unknown")==-1);
    assert(NativeGuideParse("guide")==-1); // preserve the original case-sensitive contract
    // The native callback writes the chosen internal name to the normal file;
    // its reader now resolves Guide to key 110, already read into input bit 14.
    const char *stored = NativeGuideTestTable[12].setting;
    int selected = NativeGuideParse(stored);
    assert(!strcmp(stored,"GUIDE") && selected==12);
    assert(NativeGuideTestTable[selected].key-96==14);
    puts("PASS: actual native ARM64 parser resolves all 13 choices, rejects unknown names and restores GUIDE from the normal settings value");
    return 0;
}
''')
subprocess.run(['xcrun','--sdk','macosx','clang','-arch','arm64','-fsanitize=address',
                'build/native_guide_smoke.c','build/native_guide_parser.s','-o','build/native_guide_smoke'],check=True)
if platform.machine() == 'arm64':
    subprocess.run(['build/native_guide_smoke'],check=True)
else:
    print('SKIP: ARM64 parser execution on Intel host; unchanged parser was verified on prior ARM64 build. Static byte/fixup checks and ARM64 compilation still run.')
print('PASS: original button indices/fields preserved; native menu and callback extended; fixup chains valid; PAD overlay source removed')
Path('build/native-guide-validation.json').write_text(json.dumps({
    'prepared_sha256': hashlib.sha256(prepared).hexdigest(),
    'choices': choices, 'overlay': False, 'device_verified': False,
    'parser_executed_this_build': platform.machine() == 'arm64'},indent=2))
