// Request the device's native high-refresh display mode without an overlay or counters.
#import <UIKit/UIKit.h>
#import <QuartzCore/QuartzCore.h>

static CADisplayLink *refreshRequest;
@interface Port0rRefreshRequest : NSObject @end
@implementation Port0rRefreshRequest
- (void)tick:(CADisplayLink *)link {}
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
}
__attribute__((constructor)) static void InstallRefreshRequest(void) {
    NSNotificationCenter *nc = NSNotificationCenter.defaultCenter;
    for (NSString *name in @[UIApplicationDidBecomeActiveNotification, UIApplicationWillResignActiveNotification,
                            UIApplicationDidEnterBackgroundNotification])
        [nc addObserverForName:name object:nil queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification *n) {
            if ([n.name isEqualToString:UIApplicationDidBecomeActiveNotification]) ConfigureRefreshRequest();
            else refreshRequest.paused = YES;
        }];
    dispatch_async(dispatch_get_main_queue(), ^{ ConfigureRefreshRequest(); });
}
