"""Apply narrowly scoped, reproducible adaptations to the pinned converter."""
from pathlib import Path
import shutil

root = Path('compatibility')
src = Path('extracted/Port0r Rally.app/Contents')
# Optional cockpit packs are game assets, not needed to build the engine.
shutil.rmtree(src / 'Resources/srallyc', ignore_errors=True)
allowed = {'Info.plist', 'MacOS/port0r', 'Frameworks/libMoltenVK.dylib',
           'Frameworks/libtcvr_mame.dylib', 'Resources/README.txt', 'Resources/AppIcon.icns',
           '_CodeSignature/CodeResources'}
unexpected = [str(p.relative_to(src)) for p in src.rglob('*')
              if p.is_file() and str(p.relative_to(src)) not in allowed]
if unexpected:
    raise SystemExit(f'Unreviewed release contents: {unexpected}')

# The Mac menu expresses resolution as percentages. Preserve those code paths;
# make their base size and backing scale match the actual iPhone/iPad screen.
p = root / 'shim/overrides/CoreGraphics.m'
s = p.read_text().replace('static double gHz = 120;', 'static double gHz = 60;\nstatic CGFloat gScale = 1;')
s = s.replace('CGSize s = UIScreen.mainScreen.nativeBounds.size;',
              'gScale = UIScreen.mainScreen.nativeScale;\n    CGSize s = UIScreen.mainScreen.nativeBounds.size;')
s = s.replace('ScreenPixels().width / 2', 'ScreenPixels().width / gScale')
s = s.replace('ScreenPixels().height / 2', 'ScreenPixels().height / gScale')
s = s.replace('p.width / 2, p.height / 2', 'p.width / gScale, p.height / gScale')
p.write_text(s)
p = root / 'shim/overrides/AppKit.m'
s = p.read_text().replace('return @"iPad";', 'return @"iPhone / iPad Native";')
s = s.replace('CGRectMake(0, 0, 1376, 1032)',
              'CGRectMake(0, 0, MAX(UIScreen.mainScreen.bounds.size.width, UIScreen.mainScreen.bounds.size.height), MIN(UIScreen.mainScreen.bounds.size.width, UIScreen.mainScreen.bounds.size.height))')
s = s.replace(': 2.0;', ': UIScreen.mainScreen.nativeScale;')
p.write_text(s)
# Native GCController is available on iOS. Avoid the unavailable Mac HID backend.
target = root / 'shim/overrides/AppKit_Port0r.m'
target.write_text('''#import <UIKit/UIKit.h>
#include <stdlib.h>
__attribute__((constructor)) static void Port0rContainerSetup(void) {
    setenv("SDL_JOYSTICK_IOKIT", "0", 1);
    setenv("SDL_JOYSTICK_HIDAPI", "0", 1);
    setenv("SDL_JOYSTICK_MFI", "1", 1);
    NSFileManager *fm = NSFileManager.defaultManager;
    for (NSString *sub in @[@"Documents/Downloads", @"Documents/Port0r/srallyc/roms"]) {
        [fm createDirectoryAtPath:[NSHomeDirectory() stringByAppendingPathComponent:sub]
            withIntermediateDirectories:YES attributes:nil error:nil];
    }
}
''')
print('Prepared native display sizing, GameController backend and ROM-free input bundle')
