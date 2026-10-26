// Minimal owned bitmap storage for SDL's Cocoa_CreateImage. Generated AppKit
// stubs returned nil from bitmapData despite returning a successful init.
#import <Foundation/Foundation.h>
#import <CoreGraphics/CoreGraphics.h>
#include <stdint.h>

@interface NSBitmapImageRep : NSObject {
    NSMutableData *_storage;
    unsigned char *_pixels;
    NSInteger _width, _height, _stride, _samples;
    CGImageRef _image;
}
- (instancetype)initWithBitmapDataPlanes:(unsigned char **)planes
    pixelsWide:(NSInteger)width pixelsHigh:(NSInteger)height
    bitsPerSample:(NSInteger)bits samplesPerPixel:(NSInteger)samples
    hasAlpha:(BOOL)alpha isPlanar:(BOOL)planar colorSpaceName:(NSString *)space
    bytesPerRow:(NSInteger)stride bitsPerPixel:(NSInteger)pixelBits;
- (unsigned char *)bitmapData;
- (NSInteger)pixelsWide;
- (NSInteger)pixelsHigh;
- (NSInteger)bytesPerRow;
- (CGImageRef)CGImage;
@end

@implementation NSBitmapImageRep
- (instancetype)initWithBitmapDataPlanes:(unsigned char **)planes
    pixelsWide:(NSInteger)width pixelsHigh:(NSInteger)height
    bitsPerSample:(NSInteger)bits samplesPerPixel:(NSInteger)samples
    hasAlpha:(BOOL)alpha isPlanar:(BOOL)planar colorSpaceName:(NSString *)space
    bytesPerRow:(NSInteger)stride bitsPerPixel:(NSInteger)pixelBits {
    // SDL supplies 8-bit interleaved RGBA with its converted surface pitch.
    // Refuse unsupported layouts and overflow before exposing a writable buffer.
    if (width <= 0 || height <= 0 || bits != 8 || samples != 4 || planar ||
        !alpha || (pixelBits != 0 && pixelBits != 32) || width > 16384 || height > 16384) return nil;
    if (!stride) stride = width * samples;
    if (stride < width * samples || stride > (64 * 1024 * 1024) / height) return nil;
    if (!(self = [super init])) return nil;
    _width = width; _height = height; _stride = stride; _samples = samples;
    if (planes && planes[0]) {
        // AppKit leaves caller-supplied storage owned by the caller.
        _pixels = planes[0];
    } else {
        _storage = [NSMutableData dataWithLength:(NSUInteger)(stride * height)];
        _pixels = _storage.mutableBytes;
    }
    if (!_pixels) return nil;
    NSLog(@"PORT0R bitmap allocated %ldx%ld stride=%ld", (long)width, (long)height, (long)stride);
    return self;
}
- (unsigned char *)bitmapData { return _pixels; }
- (NSInteger)pixelsWide { return _width; }
- (NSInteger)pixelsHigh { return _height; }
- (NSInteger)bytesPerRow { return _stride; }
- (void)dealloc { if (_image) CGImageRelease(_image); }
- (CGImageRef)CGImage {
    if (_image) return _image;
    CGDataProviderRef provider = CGDataProviderCreateWithCFData((__bridge CFDataRef)
        [NSData dataWithBytes:_pixels length:(NSUInteger)(_stride * _height)]);
    CGColorSpaceRef color = CGColorSpaceCreateDeviceRGB();
    _image = CGImageCreate(_width, _height, 8, 32, _stride, color,
        kCGBitmapByteOrder32Big | kCGImageAlphaPremultipliedLast, provider, NULL, false,
        kCGRenderingIntentDefault);
    CGDataProviderRelease(provider);
    CGColorSpaceRelease(color);
    // Kept by the owning bitmap representation, as AppKit's getter requires.
    return _image;
}
@end

@interface NSImage : NSObject {
    CGSize _size;
    NSMutableArray *_representations;
}
- (instancetype)initWithSize:(CGSize)size;
- (void)addRepresentation:(id)representation;
- (NSArray *)representations;
- (CGSize)size;
@end
@implementation NSImage
- (instancetype)initWithSize:(CGSize)size {
    if ((self = [super init])) { _size = size; _representations = [NSMutableArray new]; }
    return self;
}
- (void)addRepresentation:(id)representation { if (representation) [_representations addObject:representation]; }
- (NSArray *)representations { return [_representations copy]; }
- (CGSize)size { return _size; }
- (CGImageRef)CGImageForProposedRect:(CGRect *)rect context:(id)context hints:(NSDictionary *)hints {
    return [(NSBitmapImageRep *)_representations.firstObject CGImage];
}
@end
