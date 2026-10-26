#import <UIKit/UIKit.h>
#import <GameController/GameController.h>
#include "Port0rTouchState.h"
extern void Port0rTouchKey(unsigned short code, BOOL down);
static Port0rTouchState touchState;
static void EmitTouch(unsigned short key, bool down) { Port0rTouchKey(key, down); }

@interface Port0rTouchButton : UIButton {
    unsigned short _port0rMacKey;
    BOOL _port0rKeyHeld;
}
@property unsigned short macKey;
@property BOOL port0rKeyHeld;
- (void)releaseKey;
@end
@implementation Port0rTouchButton
@synthesize macKey = _port0rMacKey;
@synthesize port0rKeyHeld = _port0rKeyHeld;
- (void)pressKey {
    if (self.port0rKeyHeld || !touchState.enabled) return;
    self.port0rKeyHeld = YES; self.alpha = 1;
    Port0rTouchChange(&touchState, self.macKey, true, EmitTouch);
}
- (void)releaseKey {
    if (!self.port0rKeyHeld) return;
    self.port0rKeyHeld = NO; self.alpha = 0.65;
    Port0rTouchChange(&touchState, self.macKey, false, EmitTouch);
}
@end
@interface Port0rTouchOverlay : UIView @end
@implementation Port0rTouchOverlay
- (UIView *)hitTest:(CGPoint)point withEvent:(UIEvent *)event {
    UIView *hit = [super hitTest:point withEvent:event];
    return hit == self ? nil : hit; // empty space continues to the game
}
@end
static Port0rTouchOverlay *touchOverlay;
static NSMutableArray<Port0rTouchButton *> *touchButtons;
static void ReleaseTouch(void) {
    for (Port0rTouchButton *button in touchButtons) [button releaseKey];
    Port0rTouchSetEnabled(&touchState, false, EmitTouch);
}
static Port0rTouchButton *AddButton(NSString *title, NSString *label, unsigned short key,
                                   CGFloat width, CGFloat height) {
    Port0rTouchButton *button = [Port0rTouchButton buttonWithType:UIButtonTypeCustom];
    button.macKey = key;
    button.alpha = 0.65;
    button.backgroundColor = [UIColor.blackColor colorWithAlphaComponent:0.7];
    button.layer.cornerRadius = 12;
    button.layer.borderWidth = 1;
    button.layer.borderColor = [UIColor.whiteColor colorWithAlphaComponent:0.6].CGColor;
    button.titleLabel.font = [UIFont systemFontOfSize:16 weight:UIFontWeightBold];
    [button setTitle:title forState:UIControlStateNormal];
    [button setTitleColor:UIColor.whiteColor forState:UIControlStateNormal];
    button.accessibilityLabel = label;
    button.exclusiveTouch = NO;
    button.translatesAutoresizingMaskIntoConstraints = NO;
    [button addTarget:button action:@selector(pressKey) forControlEvents:UIControlEventTouchDown | UIControlEventTouchDragEnter];
    [button addTarget:button action:@selector(releaseKey) forControlEvents:UIControlEventTouchUpInside | UIControlEventTouchUpOutside | UIControlEventTouchCancel | UIControlEventTouchDragExit];
    [touchOverlay addSubview:button];
    [touchButtons addObject:button];
    [NSLayoutConstraint activateConstraints:@[[button.widthAnchor constraintEqualToConstant:width],
                                              [button.heightAnchor constraintEqualToConstant:height]]];
    return button;
}
static void Place(Port0rTouchButton *button, CGFloat horizontal, CGFloat bottom, BOOL right) {
    UILayoutGuide *safe = touchOverlay.safeAreaLayoutGuide;
    NSLayoutConstraint *x = right ? [button.trailingAnchor constraintEqualToAnchor:safe.trailingAnchor constant:-horizontal]
                                 : [button.leadingAnchor constraintEqualToAnchor:safe.leadingAnchor constant:horizontal];
    [NSLayoutConstraint activateConstraints:@[x, [button.bottomAnchor constraintEqualToAnchor:safe.bottomAnchor constant:-bottom]]];
}
static void CreateTouch(UIWindow *window) {
    ReleaseTouch();
    [touchOverlay removeFromSuperview];
    touchButtons = [NSMutableArray new];
    touchOverlay = [[Port0rTouchOverlay alloc] initWithFrame:window.bounds];
    touchOverlay.backgroundColor = UIColor.clearColor;
    touchOverlay.multipleTouchEnabled = YES;
    touchOverlay.autoresizingMask = UIViewAutoresizingFlexibleWidth | UIViewAutoresizingFlexibleHeight;
    touchOverlay.accessibilityIdentifier = @"Port0rTouchControls";
    [window addSubview:touchOverlay];
    Place(AddButton(@"◀", @"왼쪽 조향", 123, 54, 54), 10, 76, NO);
    Place(AddButton(@"▶", @"오른쪽 조향", 124, 54, 54), 126, 76, NO);
    Place(AddButton(@"▲", @"위 / 가속", 126, 54, 54), 68, 134, NO);
    Place(AddButton(@"▼", @"아래 / 브레이크", 125, 54, 54), 68, 18, NO);
    Place(AddButton(@"GAS", @"가속", 126, 76, 76), 10, 20, YES);
    Place(AddButton(@"BRAKE", @"브레이크", 125, 76, 76), 94, 20, YES);
    Place(AddButton(@"G+", @"기어 올리기", 14, 52, 42), 10, 110, YES);
    Place(AddButton(@"G−", @"기어 내리기", 12, 52, 42), 70, 110, YES);
    Place(AddButton(@"VIEW", @"시점 전환", 9, 56, 42), 130, 110, YES);
    NSArray *titles = @[@"COIN", @"START", @"MENU"];
    NSArray *labels = @[@"동전", @"시작 / 확인", @"설정 / 뒤로"];
    unsigned short keys[] = {23, 36, 53};
    for (int i = 0; i < 3; ++i) {
        Port0rTouchButton *button = AddButton(titles[i], labels[i], keys[i], 66, 38);
        [NSLayoutConstraint activateConstraints:@[
            [button.centerXAnchor constraintEqualToAnchor:touchOverlay.safeAreaLayoutGuide.centerXAnchor constant:(i-1)*74],
            [button.bottomAnchor constraintEqualToAnchor:touchOverlay.safeAreaLayoutGuide.bottomAnchor constant:-16]]];
    }
}
static void UpdateTouch(void) {
    if (!touchOverlay.window) {
        for (UIScene *scene in UIApplication.sharedApplication.connectedScenes) {
            if (![scene isKindOfClass:UIWindowScene.class]) continue;
            for (UIWindow *window in ((UIWindowScene *)scene).windows) {
                if ([NSStringFromClass(window.rootViewController.class) isEqualToString:@"ShimViewController"]) {
                    CreateTouch(window); break;
                }
            }
            if (touchOverlay.window) break;
        }
    }
    BOOL enabled = GCController.controllers.count == 0 && UIApplication.sharedApplication.applicationState == UIApplicationStateActive;
    if (!enabled) ReleaseTouch();
    Port0rTouchSetEnabled(&touchState, enabled, EmitTouch);
    touchOverlay.hidden = !enabled;
}
__attribute__((constructor)) static void InstallTouch(void) {
    NSNotificationCenter *nc = NSNotificationCenter.defaultCenter;
    for (NSString *name in @[GCControllerDidConnectNotification, GCControllerDidDisconnectNotification,
                            UIApplicationDidBecomeActiveNotification, UIApplicationWillResignActiveNotification])
        [nc addObserverForName:name object:nil queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification *n) {
            if ([n.name isEqualToString:UIApplicationWillResignActiveNotification]) { ReleaseTouch(); touchOverlay.hidden = YES; }
            else dispatch_async(dispatch_get_main_queue(), ^{ UpdateTouch(); });
        }];
    dispatch_async(dispatch_get_main_queue(), ^{
        static dispatch_source_t timer;
        timer = dispatch_source_create(DISPATCH_SOURCE_TYPE_TIMER, 0, 0, dispatch_get_main_queue());
        dispatch_source_set_timer(timer, dispatch_time(DISPATCH_TIME_NOW, 0), NSEC_PER_SEC, 50*NSEC_PER_MSEC);
        dispatch_source_set_event_handler(timer, ^{ UpdateTouch(); });
        dispatch_resume(timer);
    });
}
