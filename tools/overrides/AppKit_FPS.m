// Count completed Metal presentations, independently of the main/UI run loop.
#import <UIKit/UIKit.h>
#import <Metal/Metal.h>
#import <QuartzCore/QuartzCore.h>
#import <objc/runtime.h>
#import <stdatomic.h>

static _Atomic uint64_t presentedFrames;
static _Atomic uint64_t requestedFrames;
static _Atomic uint64_t outputPixels;
static IMP originalNextDrawable;
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
                fpsLabel.numberOfLines = 2;
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
                    [fpsLabel.widthAnchor constraintEqualToConstant:285],
                    [fpsLabel.heightAnchor constraintEqualToConstant:42]]];
                break;
            }
            if (fpsLabel) break;
        }
    }
    CFTimeInterval now = CACurrentMediaTime();
    uint64_t frames = atomic_exchange_explicit(&presentedFrames, 0, memory_order_relaxed);
    uint64_t requests = atomic_exchange_explicit(&requestedFrames, 0, memory_order_relaxed);
    uint64_t pixels = atomic_load_explicit(&outputPixels, memory_order_relaxed);
    double elapsed = lastUpdate ? now - lastUpdate : 0;
    lastUpdate = now;
    if (elapsed > 0 && fpsLabel) {
        // A rendered/presented frame can repeat the same emulated arcade frame.
        // The closed-source core's frame-counter ABI is not documented, so do
        // not call an unknown export or display a guessed constant 60 as a measurement.
        fpsLabel.text = [NSString stringWithFormat:@"Present %.1f | Render %.1f\nGame FPS -- | Output %ux%u",
                         frames / elapsed, requests / elapsed, (unsigned)(pixels >> 32), (unsigned)pixels];
        [fpsLabel.superview bringSubviewToFront:fpsLabel];
    }
}
__attribute__((constructor)) static void InstallFPS(void) {
    Method method = class_getInstanceMethod(CAMetalLayer.class, @selector(nextDrawable));
    if (method) originalNextDrawable = method_setImplementation(method, (IMP)FPSNextDrawable);
    dispatch_async(dispatch_get_main_queue(), ^{
        static dispatch_source_t timer;
        timer = dispatch_source_create(DISPATCH_SOURCE_TYPE_TIMER, 0, 0, dispatch_get_main_queue());
        dispatch_source_set_timer(timer, dispatch_time(DISPATCH_TIME_NOW, NSEC_PER_SEC), NSEC_PER_SEC, 50*NSEC_PER_MSEC);
        dispatch_source_set_event_handler(timer, ^{ UpdateFPS(); });
        dispatch_resume(timer);
    });
}
