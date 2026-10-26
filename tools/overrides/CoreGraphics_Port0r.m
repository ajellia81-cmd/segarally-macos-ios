#import <Foundation/Foundation.h>
#include <stdint.h>

#define EXPORT __attribute__((visibility("default")))
EXPORT int CGDisplayIsMain(uint32_t display) { return display == 1; }
EXPORT uint32_t CGDisplayMirrorsDisplay(uint32_t display) { return 0; }
// Synthetic identifier consumed only by our IODisplayCreateInfoDictionary.
EXPORT uint32_t CGDisplayIOServicePort(uint32_t display) { return display == 1 ? 1 : 0; }
EXPORT CFStringRef CGDisplayModeCopyPixelEncoding(const void *mode) {
    // IOGraphicsTypes.h IO32BitDirectPixels, expected by SDL's pixel-format parser.
    return (CFStringRef)CFRetain(CFSTR("--------RRRRRRRRGGGGGGGGBBBBBBBB"));
}
EXPORT int32_t CGDisplaySetDisplayMode(uint32_t display, const void *mode, CFDictionaryRef options) {
    // iOS has one native mode; SDL resizes its drawable, not the physical screen.
    return display == 1 && mode ? 0 : 1001;
}
