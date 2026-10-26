#import <Foundation/Foundation.h>
#import <AudioToolbox/AudioToolbox.h>
#import <TargetConditionals.h>
#import <dlfcn.h>
#if TARGET_OS_IOS
#import <AVFAudio/AVFAudio.h>
#endif

static void ActivateOutput(void) {
#if TARGET_OS_IOS
    AVAudioSession *session = AVAudioSession.sharedInstance;
    NSError *error = nil;
    BOOL category = [session setCategory:AVAudioSessionCategoryPlayback mode:AVAudioSessionModeDefault options:0 error:&error];
    BOOL active = category && [session setActive:YES error:&error];
    NSLog(@"PORT0R audio session active=%d rate=%.0f volume=%.2f route=%@ error=%@",
          active, session.sampleRate, session.outputVolume, session.currentRoute.outputs, error);
#endif
}
static void *AudioFunction(const char *name) {
    static void *library;
    static dispatch_once_t once;
    dispatch_once(&once, ^{ library = dlopen("/System/Library/Frameworks/AudioToolbox.framework/AudioToolbox", RTLD_LAZY); });
    return library ? dlsym(library, name) : NULL;
}
__attribute__((visibility("default")))
OSStatus AudioQueueNewOutput(const AudioStreamBasicDescription *format, AudioQueueOutputCallback callback,
    void *context, CFRunLoopRef runloop, CFStringRef mode, UInt32 flags, AudioQueueRef *queue) {
    ActivateOutput();
    OSStatus (*real)(const AudioStreamBasicDescription *, AudioQueueOutputCallback, void *, CFRunLoopRef, CFStringRef, UInt32, AudioQueueRef *) = AudioFunction("AudioQueueNewOutput");
    OSStatus status = real ? real(format, callback, context, runloop, mode, flags, queue) : kAudio_ParamError;
    NSLog(@"PORT0R AudioQueueNewOutput status=%d rate=%.0f channels=%u", (int)status,
          format ? format->mSampleRate : 0, format ? (unsigned)format->mChannelsPerFrame : 0);
    return status;
}
__attribute__((visibility("default")))
OSStatus AudioQueueSetProperty(AudioQueueRef queue, AudioQueuePropertyID property, const void *data, UInt32 size) {
    if (property == (AudioQueuePropertyID)'aqcd' && data && size == sizeof(CFStringRef)) {
        CFStringRef uid = *(CFStringRef const *)data;
        if (uid && CFEqual(uid, CFSTR("Port0r-iOS-default-output"))) {
            NSLog(@"PORT0R AudioQueue uses native iOS default route");
            return noErr;
        }
    }
    OSStatus (*real)(AudioQueueRef, AudioQueuePropertyID, const void *, UInt32) = AudioFunction("AudioQueueSetProperty");
    return real ? real(queue, property, data, size) : kAudio_ParamError;
}
__attribute__((visibility("default")))
OSStatus AudioQueueStart(AudioQueueRef queue, const AudioTimeStamp *start) {
    ActivateOutput();
    OSStatus (*real)(AudioQueueRef, const AudioTimeStamp *) = AudioFunction("AudioQueueStart");
    OSStatus status = real ? real(queue, start) : kAudio_ParamError;
    NSLog(@"PORT0R AudioQueueStart status=%d", (int)status);
    return status;
}
