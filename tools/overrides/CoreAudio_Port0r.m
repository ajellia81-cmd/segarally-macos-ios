// Present one logical iOS default-output device to SDL's Mac CoreAudio backend.
// Actual PCM playback/routing remains in the native iOS AudioQueue APIs.
#import <Foundation/Foundation.h>
#import <AudioToolbox/AudioToolbox.h>
#import <TargetConditionals.h>
#if TARGET_OS_IOS
#import <AVFAudio/AVFAudio.h>
#endif
#include <string.h>

typedef struct { uint32_t selector, scope, element; } Port0rAudioAddress;
typedef OSStatus (*Port0rAudioListener)(uint32_t, uint32_t, const Port0rAudioAddress *, void *);
enum { Port0rSystem = 1, Port0rOutput = 2 };

static OSStatus CopyValue(uint32_t *size, void *out, const void *value, uint32_t bytes) {
    if (!size || !out || *size < bytes) return (OSStatus)'!siz';
    memcpy(out, value, bytes); *size = bytes; return noErr;
}
static double OutputRate(void) {
#if TARGET_OS_IOS
    double rate = AVAudioSession.sharedInstance.sampleRate;
    return rate > 0 ? rate : 48000;
#else
    return 48000;
#endif
}
OSStatus Port0rAudioGet(uint32_t object, const Port0rAudioAddress *a, uint32_t qualifierSize,
                       const void *qualifier, uint32_t *size, void *out) __asm__("_AudioObjectGetPropertyData");
__attribute__((visibility("default")))
OSStatus Port0rAudioGet(uint32_t object, const Port0rAudioAddress *a, uint32_t qualifierSize,
                       const void *qualifier, uint32_t *size, void *out) {
    if (!a || (object != Port0rSystem && object != Port0rOutput)) return (OSStatus)'!obj';
    uint32_t value = Port0rOutput;
    switch (a->selector) {
    case 'dev#': case 'dOut': case 'sOut':
        return CopyValue(size, out, &value, sizeof value);
    case 'dIn ': return (OSStatus)'!dev'; // no microphone emulation/permission
    case 'livn': value = 1; return CopyValue(size, out, &value, sizeof value);
    case 'oink': { int32_t pid = -1; return CopyValue(size, out, &pid, sizeof pid); }
    case 'nsrt': { double rate = OutputRate(); return CopyValue(size, out, &rate, sizeof rate); }
    case 'slay': {
        AudioBufferList buffers = {0};
        buffers.mNumberBuffers = 1;
        buffers.mBuffers[0].mNumberChannels = a->scope == 'inpt' ? 0 : 2;
        return CopyValue(size, out, &buffers, sizeof buffers);
    }
    case 'lnam': case 'uid ': {
        if (!size || !out || *size < sizeof(CFStringRef)) return (OSStatus)'!siz';
        CFStringRef text = (CFStringRef)CFRetain(a->selector == 'uid ' ? CFSTR("Port0r-iOS-default-output") : CFSTR("iOS Default Output"));
        return CopyValue(size, out, &text, sizeof text);
    }
    default:
        NSLog(@"PORT0R unsupported CoreAudio property %08x", (unsigned)a->selector);
        return (OSStatus)'who?';
    }
}
OSStatus Port0rAudioSize(uint32_t object, const Port0rAudioAddress *a, uint32_t qs,
                        const void *q, uint32_t *size) __asm__("_AudioObjectGetPropertyDataSize");
__attribute__((visibility("default")))
OSStatus Port0rAudioSize(uint32_t object, const Port0rAudioAddress *a, uint32_t qs, const void *q, uint32_t *size) {
    if (!a || !size || (object != 1 && object != 2)) return (OSStatus)'!obj';
    switch (a->selector) {
    case 'dev#': case 'dOut': case 'sOut': case 'livn': case 'oink': *size = 4; break;
    case 'lnam': case 'uid ': *size = sizeof(CFStringRef); break;
    case 'nsrt': *size = sizeof(double); break;
    case 'slay': *size = sizeof(AudioBufferList); break;
    default: return (OSStatus)'who?';
    }
    return noErr;
}
OSStatus Port0rAudioAdd(uint32_t, const Port0rAudioAddress *, Port0rAudioListener, void *) __asm__("_AudioObjectAddPropertyListener");
OSStatus Port0rAudioRemove(uint32_t, const Port0rAudioAddress *, Port0rAudioListener, void *) __asm__("_AudioObjectRemovePropertyListener");
__attribute__((visibility("default"))) OSStatus Port0rAudioAdd(uint32_t object, const Port0rAudioAddress *a, Port0rAudioListener cb, void *ctx) {
    // The logical endpoint is stable; AudioQueue follows AVAudioSession routing.
    return a && cb && (object == 1 || object == 2) ? noErr : (OSStatus)'!obj';
}
__attribute__((visibility("default"))) OSStatus Port0rAudioRemove(uint32_t object, const Port0rAudioAddress *a, Port0rAudioListener cb, void *ctx) {
    return a && cb && (object == 1 || object == 2) ? noErr : (OSStatus)'!obj';
}
