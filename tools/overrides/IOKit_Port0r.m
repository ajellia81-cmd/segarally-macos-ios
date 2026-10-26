// SDL Cocoa_GetDisplayName releases this dictionary unconditionally.
// Return a real retained CF object instead of the generated NULL stub.
#import <Foundation/Foundation.h>
#include <stdint.h>

__attribute__((visibility("default")))
CFDictionaryRef IODisplayCreateInfoDictionary(uint32_t service, uint32_t options) {
    NSDictionary *info = @{ @"DisplayProductName": @{ @"en_US": @"iPhone / iPad Native" } };
    NSLog(@"PORT0R IODisplayCreateInfoDictionary: retained display metadata");
    return CFBridgingRetain(info);
}
