// The closed-source desktop menu's twelve-button table omits Guide. Keep that
// menu intact and provide an additional iOS Guide assignment in the PAD panel.
#import <UIKit/UIKit.h>
#import <GameController/GameController.h>
#import <objc/runtime.h>
#include "Port0rTouchState.h"
extern void Port0rTouchKey(unsigned short code, BOOL down);
static const char guideHeldKey;
static Port0rTouchState guideState;
static NSInteger guideKey = -1;
static UIButton *settingsButton;
static NSString *GuideSettingsPath(void) {
    return [NSHomeDirectory() stringByAppendingPathComponent:@"Documents/Port0r/ios-controller.plist"];
}
static void GuideEmit(unsigned short code, bool down) { Port0rTouchKey(code, down); }
static NSString *GuideTitle(NSInteger key) {
    switch (key) {
        case 23: return @"동전 / Coin";
        case 36: return @"시작 / Start";
        case 53: return @"메뉴 / Menu";
        case 9: return @"시점 / View";
        case 14: return @"기어 올리기 / Gear +";
        case 12: return @"기어 내리기 / Gear −";
        default: return @"지정 안 함 / Unassigned";
    }
}
static void ReleaseGuides(void) {
    Port0rTouchSetEnabled(&guideState, false, GuideEmit);
    for (GCController *controller in GCController.controllers) {
        GCControllerButtonInput *button = controller.extendedGamepad.buttonHome;
        if (button) objc_setAssociatedObject(button, &guideHeldKey, nil, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    }
}
static BOOL SaveGuide(NSInteger key) {
    NSString *path = GuideSettingsPath();
    [NSFileManager.defaultManager createDirectoryAtPath:path.stringByDeletingLastPathComponent
        withIntermediateDirectories:YES attributes:nil error:nil];
    return [@{@"guideKey": @(key)} writeToFile:path atomically:YES];
}
static void ConfigureGuides(void) {
    for (GCController *controller in GCController.controllers) {
        GCControllerButtonInput *button = controller.extendedGamepad.buttonHome;
        if (!button) continue; // a vendor-reserved button cannot be invented
        button.preferredSystemGestureState = guideKey >= 0 ? GCSystemGestureStateDisabled : GCSystemGestureStateEnabled;
        // Use an associated copy of our handler so repeated foreground/connect
        // notifications do not chain another copy onto the existing handler.
        static const char handlerKey;
        if (objc_getAssociatedObject(button, &handlerKey)) continue;
        GCControllerButtonValueChangedHandler previous = button.pressedChangedHandler;
        GCControllerButtonValueChangedHandler handler = ^(GCControllerButtonInput *input, float value, BOOL pressed) {
            if (previous) previous(input, value, pressed);
            dispatch_async(dispatch_get_main_queue(), ^{
                NSNumber *held = objc_getAssociatedObject(input, &guideHeldKey);
                if (pressed) {
                    if (held || guideKey < 0 || UIApplication.sharedApplication.applicationState != UIApplicationStateActive) return;
                    Port0rTouchSetEnabled(&guideState, true, GuideEmit);
                    objc_setAssociatedObject(input, &guideHeldKey, @(guideKey), OBJC_ASSOCIATION_RETAIN_NONATOMIC);
                    Port0rTouchChange(&guideState, (unsigned short)guideKey, true, GuideEmit);
                } else if (held) {
                    Port0rTouchChange(&guideState, held.unsignedShortValue, false, GuideEmit);
                    objc_setAssociatedObject(input, &guideHeldKey, nil, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
                }
            });
        };
        button.pressedChangedHandler = handler;
        objc_setAssociatedObject(button, &handlerKey, handler, OBJC_ASSOCIATION_COPY_NONATOMIC);
        NSLog(@"PORT0R Guide available controller=%@ assignment=%@", controller.vendorName, GuideTitle(guideKey));
    }
}
static void RefreshGuidePanel(void);
static void ShowGuideSettings(void) {
    UIViewController *root = settingsButton.window.rootViewController;
    if (!root || root.presentedViewController) return;
    BOOL available = NO;
    for (GCController *controller in GCController.controllers) if (controller.extendedGamepad.buttonHome) available = YES;
    UIAlertController *panel = [UIAlertController alertControllerWithTitle:@"게임패드 · Guide"
        message:available ? @"Guide 버튼에 지정할 동작을 선택하세요. 다른 버튼 설정은 게임의 기존 메뉴를 사용합니다."
                          : @"연결된 패드가 iOS에 Guide 입력을 제공하지 않습니다. 설정을 저장할 수 있지만 버튼 동작은 패드 지원이 필요합니다."
        preferredStyle:UIAlertControllerStyleAlert];
    for (NSNumber *choice in @[@(-1), @23, @36, @53, @9, @14, @12]) {
        NSInteger key = choice.integerValue;
        NSString *title = [NSString stringWithFormat:@"%@%@", key == guideKey ? @"✓ " : @"", GuideTitle(key)];
        [panel addAction:[UIAlertAction actionWithTitle:title style:UIAlertActionStyleDefault handler:^(UIAlertAction *action) {
            if (!SaveGuide(key)) {
                NSLog(@"PORT0R Guide assignment save failed");
                return;
            }
            ReleaseGuides(); guideKey = key; ConfigureGuides(); RefreshGuidePanel();
        }]];
    }
    [panel addAction:[UIAlertAction actionWithTitle:@"닫기" style:UIAlertActionStyleCancel handler:nil]];
    [root presentViewController:panel animated:YES completion:nil];
}
static void RefreshGuidePanel(void) {
    if (!settingsButton.window) {
        settingsButton = nil;
        for (UIScene *scene in UIApplication.sharedApplication.connectedScenes) {
            if (![scene isKindOfClass:UIWindowScene.class]) continue;
            for (UIWindow *window in ((UIWindowScene *)scene).windows) {
                if (![NSStringFromClass(window.rootViewController.class) isEqualToString:@"ShimViewController"]) continue;
                settingsButton = [UIButton buttonWithType:UIButtonTypeSystem];
                [settingsButton setTitle:@"PAD" forState:UIControlStateNormal];
                [settingsButton setTitleColor:UIColor.whiteColor forState:UIControlStateNormal];
                settingsButton.backgroundColor = [UIColor.blackColor colorWithAlphaComponent:0.65];
                settingsButton.layer.cornerRadius = 7;
                settingsButton.translatesAutoresizingMaskIntoConstraints = NO;
                settingsButton.accessibilityLabel = @"게임패드 Guide 설정";
                [settingsButton addAction:[UIAction actionWithHandler:^(UIAction *action) { ShowGuideSettings(); }]
                    forControlEvents:UIControlEventTouchUpInside];
                [window addSubview:settingsButton];
                [NSLayoutConstraint activateConstraints:@[
                    [settingsButton.topAnchor constraintEqualToAnchor:window.safeAreaLayoutGuide.topAnchor constant:4],
                    [settingsButton.trailingAnchor constraintEqualToAnchor:window.safeAreaLayoutGuide.trailingAnchor constant:-8],
                    [settingsButton.widthAnchor constraintEqualToConstant:52],
                    [settingsButton.heightAnchor constraintEqualToConstant:34]]];
                break;
            }
            if (settingsButton) break;
        }
    }
    settingsButton.hidden = GCController.controllers.count == 0 ||
        UIApplication.sharedApplication.applicationState != UIApplicationStateActive;
    if (!settingsButton.hidden) [settingsButton.superview bringSubviewToFront:settingsButton];
}
__attribute__((constructor)) static void InstallGuideSettings(void) {
    NSDictionary *saved = [NSDictionary dictionaryWithContentsOfFile:GuideSettingsPath()];
    NSInteger stored = [saved[@"guideKey"] integerValue];
    if (saved && [@[@(-1), @23, @36, @53, @9, @14, @12] containsObject:@(stored)]) guideKey = stored;
    NSNotificationCenter *nc = NSNotificationCenter.defaultCenter;
    for (NSString *name in @[GCControllerDidConnectNotification, GCControllerDidDisconnectNotification,
                            UIApplicationDidBecomeActiveNotification, UIApplicationWillResignActiveNotification])
        [nc addObserverForName:name object:nil queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification *n) {
            ReleaseGuides(); ConfigureGuides(); RefreshGuidePanel();
        }];
    dispatch_async(dispatch_get_main_queue(), ^{
        ConfigureGuides();
        static dispatch_source_t timer;
        timer = dispatch_source_create(DISPATCH_SOURCE_TYPE_TIMER, 0, 0, dispatch_get_main_queue());
        dispatch_source_set_timer(timer, DISPATCH_TIME_NOW, NSEC_PER_SEC, NSEC_PER_SEC / 10);
        dispatch_source_set_event_handler(timer, ^{ RefreshGuidePanel(); });
        dispatch_resume(timer);
    });
}
