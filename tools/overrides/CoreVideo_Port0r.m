// SDL's Cocoa display enumeration treats CVDisplayLink as optional when
// CGDisplayModeGetRefreshRate supplies the refresh rate. iOS has no CVDisplayLink.
// Report an explicit failure and initialize out parameters instead of pretending
// success with an uninitialized handle. No synthetic vsync/pacing is claimed.
#import <Foundation/Foundation.h>
#include <stdint.h>
#define EXPORT __attribute__((visibility("default")))
typedef struct { int64_t timeValue; int32_t timeScale; int32_t flags; } Port0rCVTime;
EXPORT int32_t CVDisplayLinkCreateWithCGDisplay(uint32_t display, void **link) {
    if (link) *link = NULL;
    NSLog(@"PORT0R CVDisplayLink unavailable: use native CGDisplayMode refresh rate");
    return -6660;
}
EXPORT int32_t CVDisplayLinkCreateWithActiveCGDisplays(void **link) {
    return CVDisplayLinkCreateWithCGDisplay(1, link);
}
EXPORT Port0rCVTime CVDisplayLinkGetNominalOutputVideoRefreshPeriod(void *link) {
    return (Port0rCVTime){0, 0, 1}; // kCVTimeIsIndefinite
}
EXPORT void CVDisplayLinkRelease(void *link) {}
EXPORT int32_t CVDisplayLinkSetCurrentCGDisplayFromOpenGLContext(void *link, void *context, void *format) { return -6660; }
EXPORT int32_t CVDisplayLinkSetOutputCallback(void *link, void *callback, void *context) { return -6660; }
EXPORT int32_t CVDisplayLinkStart(void *link) { return -6660; }
