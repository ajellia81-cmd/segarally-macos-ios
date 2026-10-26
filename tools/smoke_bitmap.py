"""Run SDL's bitmap allocation/copy/alpha path against the actual override.

Uses macOS Foundation/CoreGraphics on Actions; does not launch the iOS game.
"""
from pathlib import Path
import subprocess

source = Path('compatibility/shim/overrides/AppKit_Bitmap.m').resolve()
test = Path('build/bitmap_smoke.m')
test.write_text('#import "' + str(source) + '"\n' + r'''
#include <assert.h>
#include <string.h>
int main(void) { @autoreleasepool {
    // Non-packed pitch verifies that the allocation includes padding per row.
    enum { width = 17, height = 11, pitch = width * 4 + 16 };
    unsigned char original[height * pitch];
    memset(original, 0x80, sizeof original);
    for (int repeat = 0; repeat < 100; ++repeat) { @autoreleasepool {
        NSBitmapImageRep *rep = [[NSBitmapImageRep alloc]
            initWithBitmapDataPlanes:NULL pixelsWide:width pixelsHigh:height
            bitsPerSample:8 samplesPerPixel:4 hasAlpha:YES isPlanar:NO
            colorSpaceName:@"NSDeviceRGBColorSpace" bytesPerRow:pitch bitsPerPixel:32];
        assert(rep && rep.bitmapData && rep.bytesPerRow == pitch);
        unsigned char *pixels = rep.bitmapData;
        memcpy(pixels, original, sizeof original); // The original crash path.
        assert(memcmp(pixels, original, sizeof original) == 0);
        for (int i = width * height; i--; pixels += 4) {
            unsigned char alpha = pixels[3];
            for (int c = 0; c < 3; ++c) pixels[c] = (unsigned char)((pixels[c] * alpha) / 255);
        }
        NSImage *image = [[NSImage alloc] initWithSize:CGSizeMake(width, height)];
        [image addRepresentation:rep];
        assert(image.representations.count == 1);
        CGImageRef cg = [image CGImageForProposedRect:NULL context:nil hints:nil];
        assert(cg && CGImageGetWidth(cg) == width && CGImageGetHeight(cg) == height);
    }}
    // Unsupported planar data must fail init, allowing SDL's nil fallback.
    assert(![[NSBitmapImageRep alloc] initWithBitmapDataPlanes:NULL
        pixelsWide:width pixelsHigh:height bitsPerSample:8 samplesPerPixel:4
        hasAlpha:YES isPlanar:YES colorSpaceName:nil bytesPerRow:pitch bitsPerPixel:32]);
    assert(![[NSBitmapImageRep alloc] initWithBitmapDataPlanes:NULL
        pixelsWide:width pixelsHigh:height bitsPerSample:8 samplesPerPixel:4
        hasAlpha:YES isPlanar:NO colorSpaceName:nil bytesPerRow:1 bitsPerPixel:32]);
    unsigned char external[height * pitch];
    unsigned char *planes[] = { external };
    NSBitmapImageRep *borrowed = [[NSBitmapImageRep alloc] initWithBitmapDataPlanes:planes
        pixelsWide:width pixelsHigh:height bitsPerSample:8 samplesPerPixel:4
        hasAlpha:YES isPlanar:NO colorSpaceName:nil bytesPerRow:pitch bitsPerPixel:32];
    assert(borrowed.bitmapData == external);
    puts("PASS: SDL bitmap copy, premultiply, image ownership, padded rows and invalid-layout fallback");
} return 0; }
''')
subprocess.run(['xcrun', '--sdk', 'macosx', 'clang', '-fobjc-arc', '-fsanitize=address',
                '-framework', 'Foundation', '-framework', 'CoreGraphics', str(test),
                '-o', 'build/bitmap_smoke'], check=True)
result = subprocess.run(['build/bitmap_smoke'], capture_output=True, text=True)
print(result.stdout)
if result.returncode:
    print(result.stderr[-5000:])
    raise SystemExit(result.returncode)
generated = Path('build/shims/Shim_AppKit.m').read_text()
# The converter intentionally emits @interface declarations for handwritten
# classes. Only a generated @implementation would replace the real methods.
assert '@implementation NSBitmapImageRep' not in generated
assert '@implementation NSImage\n' not in generated
print('PASS: bitmap/image classes use the handwritten implementation')
