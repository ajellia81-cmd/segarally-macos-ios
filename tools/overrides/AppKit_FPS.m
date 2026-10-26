// Count completed Metal presentations, independently of the main/UI run loop.
#import <UIKit/UIKit.h>
#import <Metal/Metal.h>
#import <QuartzCore/QuartzCore.h>
#import <objc/runtime.h>
#import <stdatomic.h>
#import <dlfcn.h>
extern uint64_t Port0rInputCallsR2(void);
extern uint64_t Port0rHapticCallsR2(void);

static _Atomic uint64_t presentedFrames;
static _Atomic uint64_t requestedFrames;
static _Atomic uint64_t outputPixels;
static IMP originalNextDrawable;
static CADisplayLink *refreshRequest;
static _Atomic uint64_t displayTicks;
@interface Port0rRefreshRequest : NSObject @end
@implementation Port0rRefreshRequest
- (void)tick:(CADisplayLink *)link {
    atomic_fetch_add_explicit(&displayTicks, 1, memory_order_relaxed);
}
@end
static void ConfigureRefreshRequest(void) {
    if (!refreshRequest) {
        refreshRequest = [CADisplayLink displayLinkWithTarget:[Port0rRefreshRequest new] selector:@selector(tick:)];
        [refreshRequest addToRunLoop:NSRunLoop.mainRunLoop forMode:NSRunLoopCommonModes];
    }
    NSInteger maximum = UIScreen.mainScreen.maximumFramesPerSecond;
    if (maximum < 1) maximum = 60;
    refreshRequest.preferredFrameRateRange = CAFrameRateRangeMake(30, maximum, maximum);
    refreshRequest.paused = UIApplication.sharedApplication.applicationState != UIApplicationStateActive;
    NSLog(@"PORT0R display refresh request max=%ld hostOptIn=%@ guestOptIn=%@ lowPower=%d", (long)maximum,
          [NSBundle.mainBundle objectForInfoDictionaryKey:@"CADisableMinimumFrameDurationOnPhone"],
          @YES, NSProcessInfo.processInfo.lowPowerModeEnabled);
}

static id<MTLDrawable> FPSNextDrawable(CAMetalLayer *self, SEL cmd) {
    id<MTLDrawable> drawable = ((id (*)(id, SEL))originalNextDrawable)(self, cmd);
    if (drawable && self.drawableSize.width > 100 && self.drawableSize.height > 100) {
        atomic_fetch_add_explicit(&requestedFrames, 1, memory_order_relaxed);
        atomic_store_explicit(&outputPixels, ((uint64_t)(uint32_t)self.drawableSize.width << 32) |
                              (uint32_t)self.drawableSize.height, memory_order_relaxed);
        [drawable addPresentedHandler:^(id<MTLDrawable> completed) {
            atomic_fetch_add_explicit(&presentedFrames, 1, memory_order_relaxed);
        }];
    }
    return drawable;
}
static UILabel *fpsLabel;
static CFTimeInterval lastUpdate;
static void UpdateFPS(void) {
    if (!fpsLabel.window) {
        fpsLabel = nil;
        for (UIScene *scene in UIApplication.sharedApplication.connectedScenes) {
            if (![scene isKindOfClass:UIWindowScene.class]) continue;
            for (UIWindow *window in ((UIWindowScene *)scene).windows) {
                if (![NSStringFromClass(window.rootViewController.class) isEqualToString:@"ShimViewController"]) continue;
                fpsLabel = [UILabel new];
                fpsLabel.text = @"Present -- | Render --\nGame FPS -- | Output --";
                fpsLabel.numberOfLines = 4;
                fpsLabel.textColor = UIColor.whiteColor;
                fpsLabel.backgroundColor = [UIColor.blackColor colorWithAlphaComponent:0.7];
                fpsLabel.font = [UIFont monospacedDigitSystemFontOfSize:12 weight:UIFontWeightSemibold];
                fpsLabel.textAlignment = NSTextAlignmentCenter;
                fpsLabel.layer.cornerRadius = 5;
                fpsLabel.clipsToBounds = YES;
                fpsLabel.userInteractionEnabled = NO;
                fpsLabel.accessibilityIdentifier = @"Port0rPresentationFPS";
                fpsLabel.translatesAutoresizingMaskIntoConstraints = NO;
                [window addSubview:fpsLabel];
                [NSLayoutConstraint activateConstraints:@[
                    [fpsLabel.topAnchor constraintEqualToAnchor:window.safeAreaLayoutGuide.topAnchor constant:4],
                    [fpsLabel.leadingAnchor constraintEqualToAnchor:window.safeAreaLayoutGuide.leadingAnchor constant:8],
                    [fpsLabel.widthAnchor constraintEqualToConstant:315],
                    [fpsLabel.heightAnchor constraintEqualToConstant:76]]];
                break;
            }
            if (fpsLabel) break;
        }
    }
    CFTimeInterval now = CACurrentMediaTime();
    uint64_t ticks = atomic_exchange_explicit(&displayTicks, 0, memory_order_relaxed);
    uint64_t frames = atomic_exchange_explicit(&presentedFrames, 0, memory_order_relaxed);
    uint64_t requests = atomic_exchange_explicit(&requestedFrames, 0, memory_order_relaxed);
    uint64_t pixels = atomic_load_explicit(&outputPixels, memory_order_relaxed);
    double elapsed = lastUpdate ? now - lastUpdate : 0;
    lastUpdate = now;
    static void *audioImage;
    if (!audioImage) {
        Dl_info image = {0};
        if (dladdr((void *)ConfigureRefreshRequest, &image) && image.dli_fname) {
            NSString *path = [[@(image.dli_fname) stringByDeletingLastPathComponent] stringByAppendingPathComponent:@"libShim_AudioToolbox.dylib"];
            audioImage = dlopen(path.fileSystemRepresentation, RTLD_NOLOAD | RTLD_LAZY);
        }
    }
    uint64_t (*audio)(void) = audioImage ? dlsym(audioImage, "Port0rAudioCallsR2") : NULL;
    uint64_t (*input)(void) = Port0rInputCallsR2;
    uint64_t (*haptic)(void) = Port0rHapticCallsR2;
    unsigned long long a = audio ? audio() : 0, b = input ? input() : 0, h = haptic ? haptic() : 0;
    static unsigned reports;
    if (!(reports++ % 5)) NSLog(@"PORT0R R5 runtime A=%llu S=%llu H=%llu audioSymbol=%d inputSymbol=%d hapticSymbol=%d",
        a,b,h,audio != NULL,input != NULL,haptic != NULL);
    if (elapsed > 0 && fpsLabel) {
        // A rendered/presented frame can repeat the same emulated arcade frame.
        // The closed-source core's frame-counter ABI is not documented, so do
        // not call an unknown export or display a guessed constant 60 as a measurement.
        fpsLabel.text = [NSString stringWithFormat:@"Present %.1f | Render %.1f\nGame FPS -- | Output %ux%u\nDisplay %.1f / Max %ld\nR5 | A %llu | S %llu | H %llu",
                         frames / elapsed, requests / elapsed, (unsigned)(pixels >> 32), (unsigned)pixels,
                         ticks / elapsed, (long)UIScreen.mainScreen.maximumFramesPerSecond, a, b, h];
        [fpsLabel.superview bringSubviewToFront:fpsLabel];
    }
}
__attribute__((constructor)) static void InstallFPS(void) {
    Method method = class_getInstanceMethod(CAMetalLayer.class, @selector(nextDrawable));
    if (method) originalNextDrawable = method_setImplementation(method, (IMP)FPSNextDrawable);
    NSNotificationCenter *nc = NSNotificationCenter.defaultCenter;
    for (NSString *name in @[UIApplicationDidBecomeActiveNotification, UIApplicationWillResignActiveNotification,
                            UIApplicationDidEnterBackgroundNotification])
        [nc addObserverForName:name object:nil queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification *n) {
            if ([n.name isEqualToString:UIApplicationDidBecomeActiveNotification]) ConfigureRefreshRequest();
            else refreshRequest.paused = YES;
        }];
    dispatch_async(dispatch_get_main_queue(), ^{
        ConfigureRefreshRequest();
        static dispatch_source_t timer;
        timer = dispatch_source_create(DISPATCH_SOURCE_TYPE_TIMER, 0, 0, dispatch_get_main_queue());
        dispatch_source_set_timer(timer, dispatch_time(DISPATCH_TIME_NOW, NSEC_PER_SEC), NSEC_PER_SEC, 50*NSEC_PER_MSEC);
        dispatch_source_set_event_handler(timer, ^{ UpdateFPS(); });
        dispatch_resume(timer);
    });
}
