"""Exercise SDL display metadata ownership on the macOS Actions runner.

This is a Foundation/CF ABI smoke test, not an iOS game launch test.
Only the screen measurement/Metal-device functions are removed from the test
translation unit; the generated mode ownership code is used verbatim.
"""
from pathlib import Path
import re
import subprocess

overrides = Path('compatibility/shim/overrides')
build = Path('build')
src = (overrides / 'CoreGraphics.m').read_text()
src = src.replace('#import <UIKit/UIKit.h>', '#import <Foundation/Foundation.h>\n#import <CoreGraphics/CGGeometry.h>')
src = src.replace('#import <Metal/Metal.h>', '')
src, count = re.subn(r'__attribute__\(\(constructor\)\) static void MeasureScreen\(void\) \{.*?\n\}', '', src, flags=re.S)
assert count == 1
src, count = re.subn(r'EXPORT id<MTLDevice> CGDirectDisplayCopyCurrentMetalDevice.*?\n\}', '', src, flags=re.S)
assert count == 1
(build / 'display_smoke_core.m').write_text(src)
(build / 'display_smoke_main.m').write_text(r'''
#import <Foundation/Foundation.h>
#include <assert.h>
extern void *CGDisplayCopyDisplayMode(uint32_t);
extern void *CGDisplayModeRetain(void *);
extern void CGDisplayModeRelease(void *);
extern CFArrayRef CGDisplayCopyAllDisplayModes(uint32_t, CFDictionaryRef);
extern CFStringRef CGDisplayModeCopyPixelEncoding(const void *);
extern CFDictionaryRef IODisplayCreateInfoDictionary(uint32_t, uint32_t);
extern int CGDisplayIsMain(uint32_t);
extern uint32_t CGDisplayMirrorsDisplay(uint32_t);
extern int32_t CVDisplayLinkCreateWithCGDisplay(uint32_t, void **);
int main(void) { @autoreleasepool {
    for (int i = 0; i < 100; ++i) {
        CFDictionaryRef info = IODisplayCreateInfoDictionary(1, 0);
        assert(info && CFGetTypeID(info) == CFDictionaryGetTypeID());
        CFDictionaryRef names = CFDictionaryGetValue(info, CFSTR("DisplayProductName"));
        assert(names && CFDictionaryGetCount(names) > 0);
        CFRelease(info); // SDL does this unconditionally; NULL stub crashes here.
        void *mode = CGDisplayCopyDisplayMode(1);
        assert(mode && CFGetTypeID(mode) == CFDictionaryGetTypeID());
        CFMutableArrayRef modes = CFArrayCreateMutable(NULL, 0, &kCFTypeArrayCallBacks);
        CFArrayAppendValue(modes, mode); // SDL retains via CF callbacks.
        CGDisplayModeRelease(mode);
        mode = (void *)CFArrayGetValueAtIndex(modes, 0);
        CGDisplayModeRetain(mode);
        CFRelease(modes);
        CFStringRef fmt = CGDisplayModeCopyPixelEncoding(mode);
        assert(CFEqual(fmt, CFSTR("--------RRRRRRRRGGGGGGGGBBBBBBBB")));
        CFRelease(fmt);
        CGDisplayModeRelease(mode);
        CFArrayRef all = CGDisplayCopyAllDisplayModes(1, NULL);
        assert(CFArrayGetCount(all) == 1);
        CFRelease(all);
    }
    void *link = (void *)0x1234;
    assert(CVDisplayLinkCreateWithCGDisplay(1, &link) != 0 && link == NULL);
    assert(CGDisplayIsMain(1) && CGDisplayMirrorsDisplay(1) == 0);
    puts("PASS: SDL display dictionary, pixel encoding, mode CF ownership and optional CVDisplayLink fallback");
} return 0; }
''')
subprocess.run(['xcrun', '--sdk', 'macosx', 'clang', '-fobjc-arc',
                '-I' + str(overrides.resolve()), '-framework', 'Foundation',
                str(build / 'display_smoke_core.m'), str(build / 'display_smoke_main.m'),
                *map(str, [
                    overrides / 'CoreGraphics_Port0r.m', overrides / 'IOKit_Port0r.m',
                    overrides / 'CoreVideo_Port0r.m']),
                '-o', str(build / 'display_smoke')], check=True)
result = subprocess.run([str(build / 'display_smoke')], capture_output=True, text=True)
print(result.stdout)
if result.returncode:
    print(result.stderr[-5000:])
    raise SystemExit(result.returncode)
for lib, symbols in {
    'IOKit': ['_IODisplayCreateInfoDictionary'],
    'CoreGraphics': ['_CGDisplayIsMain', '_CGDisplayMirrorsDisplay', '_CGDisplayModeCopyPixelEncoding'],
    'CoreVideo': ['_CVDisplayLinkCreateWithCGDisplay'],
}.items():
    generated = (build / 'shims' / f'Shim_{lib}.m').read_text()
    for symbol in symbols:
        assert f'__asm__("{symbol}")' not in generated, f'Stub still present: {symbol}'
print('PASS: corrected APIs are handwritten implementations, not generated NULL stubs')
