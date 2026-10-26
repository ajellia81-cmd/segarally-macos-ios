#import <Foundation/Foundation.h>
#import <AudioToolbox/AudioToolbox.h>
#import <TargetConditionals.h>
#import <dlfcn.h>
#include <math.h>
#include <stdint.h>
#include <stdatomic.h>
#include <stdbool.h>
#if TARGET_OS_IOS
#import <AVFAudio/AVFAudio.h>
#import <UIKit/UIKit.h>
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
#ifdef PORT0R_AUDIO_TEST
extern void *AudioFunction(const char *name);
#else
static void *AudioFunction(const char *name) {
    static void *library;
    static dispatch_once_t once;
    dispatch_once(&once, ^{ library = dlopen("/System/Library/Frameworks/AudioToolbox.framework/AudioToolbox", RTLD_LAZY); });
    return library ? dlsym(library, name) : NULL;
}
#endif
// Keep the user's playback intent separate from lifecycle-induced pauses.
static NSMutableDictionary<NSValue *, NSNumber *> *queueIntent;
static NSRecursiveLock *queueLock;
static BOOL outputActive = YES;
static NSMutableDictionary<NSValue *, NSValue *> *queueFormats;
static _Atomic uint64_t audioCallsR2;
static _Atomic bool audioMeasuredR2;
uint64_t Port0rAudioCallsR2(void) { return atomic_load(&audioCallsR2); }
static float ProbePCM(AudioQueueBufferRef buffer, AudioStreamBasicDescription format) {
    if (!buffer || !buffer->mAudioData || buffer->mAudioDataByteSize > buffer->mAudioDataBytesCapacity ||
        format.mFormatID != kAudioFormatLinearPCM || !(format.mFormatFlags & kAudioFormatFlagIsPacked) ||
        (format.mFormatFlags & (kAudioFormatFlagIsBigEndian | kAudioFormatFlagIsNonInterleaved))) return -1;
    float peak = 0;
    UInt32 samples = buffer->mAudioDataByteSize / (format.mBitsPerChannel == 16 ? 2 : 4);
    if (samples > 256) samples = 256;
    for (UInt32 i = 0; i < samples; i++) {
        float value;
        if (format.mBitsPerChannel == 16 && (format.mFormatFlags & kAudioFormatFlagIsSignedInteger) &&
            !(format.mFormatFlags & kAudioFormatFlagIsFloat)) value = ((int16_t *)buffer->mAudioData)[i] / 32768.0f;
        else if (format.mBitsPerChannel == 32 && (format.mFormatFlags & kAudioFormatFlagIsFloat)) value = ((float *)buffer->mAudioData)[i];
        else return -1;
        if (isfinite(value) && fabsf(value) > peak) peak = fabsf(value);
    }
    return peak;
}
static const float audioGain = 2.0f;
static float LimitSample(float sample) {
    if (!isfinite(sample)) return 0;
    float scaled = sample * audioGain;
    float magnitude = fabsf(scaled);
    // Fixed 2x gain; amplified peaks approach full scale smoothly.
    if (magnitude > 0.85f) scaled = copysignf(0.85f + 0.15f * tanhf((magnitude - 0.85f) / 0.15f), scaled);
    return scaled;
}
static void BoostPCM(AudioQueueBufferRef buffer, AudioStreamBasicDescription format) {
    if (!buffer || !buffer->mAudioData ||
        buffer->mAudioDataByteSize > buffer->mAudioDataBytesCapacity ||
        format.mFormatID != kAudioFormatLinearPCM ||
        !(format.mFormatFlags & kAudioFormatFlagIsPacked) ||
        (format.mFormatFlags & (kAudioFormatFlagIsBigEndian | kAudioFormatFlagIsNonInterleaved))) return;
    if (format.mBitsPerChannel == 16 && (format.mFormatFlags & kAudioFormatFlagIsSignedInteger) &&
        !(format.mFormatFlags & kAudioFormatFlagIsFloat)) {
        int16_t *samples = buffer->mAudioData;
        for (UInt32 i = 0; i < buffer->mAudioDataByteSize / 2; i++) {
            float value = LimitSample(samples[i] / 32768.0f);
            samples[i] = (int16_t)fmaxf(-32768, fminf(32767, roundf(value * 32768)));
        }
    } else if (format.mBitsPerChannel == 32 && (format.mFormatFlags & kAudioFormatFlagIsFloat)) {
        float *samples = buffer->mAudioData;
        for (UInt32 i = 0; i < buffer->mAudioDataByteSize / 4; i++) samples[i] = LimitSample(samples[i]);
    }
}
static void EnsureQueueState(void) {
    static dispatch_once_t once;
    dispatch_once(&once, ^{ queueLock = [NSRecursiveLock new]; queueIntent = [NSMutableDictionary new]; queueFormats = [NSMutableDictionary new]; });
}
static OSStatus NativeStart(AudioQueueRef queue, const AudioTimeStamp *start) {
    OSStatus (*real)(AudioQueueRef, const AudioTimeStamp *) = AudioFunction("AudioQueueStart");
    return real ? real(queue, start) : kAudio_ParamError;
}
static void OutputLifecycle(BOOL active) {
    EnsureQueueState(); [queueLock lock];
    if (outputActive != active) {
        outputActive = active;
        if (active) ActivateOutput();
        OSStatus (*pause)(AudioQueueRef) = AudioFunction("AudioQueuePause");
        for (NSValue *key in queueIntent) if (queueIntent[key].boolValue) {
            OSStatus status = active ? NativeStart((AudioQueueRef)key.pointerValue, NULL)
                                    : (pause ? pause((AudioQueueRef)key.pointerValue) : kAudio_ParamError);
            NSLog(@"PORT0R audio lifecycle active=%d status=%d", active, (int)status);
        }
    }
    [queueLock unlock];
}
#if TARGET_OS_IOS
__attribute__((constructor)) static void ObserveAudioLifecycle(void) {
    EnsureQueueState();
    outputActive = UIApplication.sharedApplication.applicationState != UIApplicationStateBackground;
    NSNotificationCenter *nc = NSNotificationCenter.defaultCenter;
    for (NSString *name in @[UIApplicationWillResignActiveNotification, UIApplicationDidEnterBackgroundNotification,
                            UISceneWillDeactivateNotification, UISceneDidEnterBackgroundNotification])
        [nc addObserverForName:name object:nil queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification *n) { OutputLifecycle(NO); }];
    for (NSString *name in @[UIApplicationDidBecomeActiveNotification, UISceneDidActivateNotification])
        [nc addObserverForName:name object:nil queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification *n) { OutputLifecycle(YES); }];
}
#endif
__attribute__((visibility("default")))
OSStatus AudioQueueNewOutput(const AudioStreamBasicDescription *format, AudioQueueOutputCallback callback,
    void *context, CFRunLoopRef runloop, CFStringRef mode, UInt32 flags, AudioQueueRef *queue) {
    EnsureQueueState();
    ActivateOutput();
    OSStatus (*real)(const AudioStreamBasicDescription *, AudioQueueOutputCallback, void *, CFRunLoopRef, CFStringRef, UInt32, AudioQueueRef *) = AudioFunction("AudioQueueNewOutput");
    OSStatus status = real ? real(format, callback, context, runloop, mode, flags, queue) : kAudio_ParamError;
    if (status == noErr && queue && *queue && format) {
        [queueLock lock];
        queueFormats[[NSValue valueWithPointer:*queue]] = [NSValue valueWithBytes:format objCType:@encode(AudioStreamBasicDescription)];
        [queueLock unlock];
        NSLog(@"PORT0R fixed audio gain=%.2fx, format=%u bits=%u flags=%u",
              audioGain, (unsigned)format->mFormatID, (unsigned)format->mBitsPerChannel, (unsigned)format->mFormatFlags);
    }
    NSLog(@"PORT0R AudioQueueNewOutput status=%d rate=%.0f channels=%u", (int)status,
          format ? format->mSampleRate : 0, format ? (unsigned)format->mChannelsPerFrame : 0);
    return status;
}
__attribute__((visibility("default")))
OSStatus AudioQueueEnqueueBuffer(AudioQueueRef queue, AudioQueueBufferRef buffer,
    UInt32 count, const AudioStreamPacketDescription *packets) {
    EnsureQueueState();
    AudioStreamBasicDescription format = {0};
    [queueLock lock];
    NSValue *stored = queueFormats[[NSValue valueWithPointer:queue]];
    if (stored) [stored getValue:&format size:sizeof format];
    [queueLock unlock];
    uint64_t calls = atomic_fetch_add(&audioCallsR2, 1);
    BOOL inspect = !atomic_load(&audioMeasuredR2);
    float before = inspect ? ProbePCM(buffer, format) : 0;
    BoostPCM(buffer, format);
    if (inspect && (before > 0 || before < 0) && !atomic_exchange(&audioMeasuredR2, true)) {
        float after = ProbePCM(buffer, format);
        NSLog(@"PORT0R R2 AUDIO calls=%llu format=%u flags=%u bits=%u bytes=%u peakBefore=%.5f peakAfter=%.5f gain=2x supported=%d",
              (unsigned long long)calls + 1, (unsigned)format.mFormatID, (unsigned)format.mFormatFlags,
              (unsigned)format.mBitsPerChannel, buffer ? (unsigned)buffer->mAudioDataByteSize : 0, before, after, before >= 0);
    }
    OSStatus (*real)(AudioQueueRef, AudioQueueBufferRef, UInt32, const AudioStreamPacketDescription *) = AudioFunction("AudioQueueEnqueueBuffer");
    return real ? real(queue, buffer, count, packets) : kAudio_ParamError;
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
    EnsureQueueState(); [queueLock lock];
    OSStatus status = noErr;
    if (outputActive) { ActivateOutput(); status = NativeStart(queue, start); }
    if (status == noErr) queueIntent[[NSValue valueWithPointer:queue]] = @YES;
    [queueLock unlock];
    NSLog(@"PORT0R AudioQueueStart status=%d", (int)status);
    return status;
}
__attribute__((visibility("default")))
OSStatus AudioQueuePause(AudioQueueRef queue) {
    EnsureQueueState(); [queueLock lock];
    OSStatus (*real)(AudioQueueRef) = AudioFunction("AudioQueuePause");
    OSStatus status = real ? real(queue) : kAudio_ParamError;
    if (status == noErr) queueIntent[[NSValue valueWithPointer:queue]] = @NO;
    [queueLock unlock]; return status;
}
__attribute__((visibility("default")))
OSStatus AudioQueueStop(AudioQueueRef queue, Boolean immediate) {
    EnsureQueueState(); [queueLock lock];
    OSStatus (*real)(AudioQueueRef, Boolean) = AudioFunction("AudioQueueStop");
    OSStatus status = real ? real(queue, immediate) : kAudio_ParamError;
    if (status == noErr) queueIntent[[NSValue valueWithPointer:queue]] = @NO;
    [queueLock unlock]; return status;
}
__attribute__((visibility("default")))
OSStatus AudioQueueDispose(AudioQueueRef queue, Boolean immediate) {
    EnsureQueueState(); [queueLock lock];
    [queueIntent removeObjectForKey:[NSValue valueWithPointer:queue]];
    [queueFormats removeObjectForKey:[NSValue valueWithPointer:queue]];
    // Do not hold our lock while native disposal waits for callbacks.
    [queueLock unlock];
    OSStatus (*real)(AudioQueueRef, Boolean) = AudioFunction("AudioQueueDispose");
    return real ? real(queue, immediate) : kAudio_ParamError;
}
