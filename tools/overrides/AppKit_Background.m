// iOS rejects GPU work submitted after entering the background. Gate only
// MoltenVK's commits, leaving UIKit/host rendering and lifecycle delivery alone.
#import <UIKit/UIKit.h>
#import <Metal/Metal.h>
#import <objc/runtime.h>
#import <dlfcn.h>
#import <stdatomic.h>
#include <stdbool.h>
#include <string.h>
static _Atomic bool gameActive = true;
static NSCondition *foregroundCondition;
static IMP nativeCommit;
static void SetGameActive(BOOL active) {
    [foregroundCondition lock];
    atomic_store_explicit(&gameActive, active, memory_order_release);
    [foregroundCondition broadcast];
    [foregroundCondition unlock];
    NSLog(@"PORT0R Metal lifecycle active=%d", active);
}
static BOOL IsGameGPUCaller(const void *caller) {
    Dl_info info = {0};
    return dladdr(caller, &info) && info.dli_fname && strstr(info.dli_fname, "libMoltenVK");
}
__attribute__((visibility("default"))) void Port0rWaitForForeground(void) {
    if (atomic_load_explicit(&gameActive, memory_order_acquire)) return;
    NSLog(@"PORT0R game loop paused until foreground");
    if (NSThread.isMainThread) {
        while (!atomic_load_explicit(&gameActive, memory_order_acquire))
            CFRunLoopRunInMode(kCFRunLoopDefaultMode, 0.05, true);
    } else {
        [foregroundCondition lock];
        while (!atomic_load_explicit(&gameActive, memory_order_acquire))
            [foregroundCondition wait];
        [foregroundCondition unlock];
    }
    NSLog(@"PORT0R game loop resumed");
}
static void GameCommit(id self, SEL cmd) {
    if (IsGameGPUCaller(__builtin_return_address(0))) Port0rWaitForForeground();
    ((void (*)(id, SEL))nativeCommit)(self, cmd);
}
extern void Port0rImportDownloads(void);
__attribute__((constructor)) static void InstallBackgroundGate(void) {
    foregroundCondition = [NSCondition new];
    atomic_store(&gameActive, UIApplication.sharedApplication.applicationState != UIApplicationStateBackground);
    NSNotificationCenter *nc = NSNotificationCenter.defaultCenter;
    for (NSString *name in @[UIApplicationWillResignActiveNotification, UIApplicationDidEnterBackgroundNotification,
                            UISceneWillDeactivateNotification, UISceneDidEnterBackgroundNotification])
        [nc addObserverForName:name object:nil queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification *n) { SetGameActive(NO); }];
    for (NSString *name in @[UIApplicationDidBecomeActiveNotification, UISceneDidActivateNotification])
        [nc addObserverForName:name object:nil queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification *n) { SetGameActive(YES);
            // Retry when returning after adding archives in Files. Serial main
            // delivery prevents a second import racing the startup import.
            Port0rImportDownloads();
        }];
    id<MTLDevice> device = MTLCreateSystemDefaultDevice();
    id<MTLCommandQueue> queue = [device newCommandQueue];
    id<MTLCommandBuffer> buffer = [queue commandBuffer];
    Method m = buffer ? class_getInstanceMethod(object_getClass(buffer), @selector(commit)) : NULL;
    if (m) nativeCommit = method_setImplementation(m, (IMP)GameCommit);
    NSLog(@"PORT0R MoltenVK background GPU gate installed=%d", nativeCommit != NULL);
}
