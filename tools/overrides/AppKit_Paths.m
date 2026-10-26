// libc++ filesystem operations do not pass through the game's libc shims.
// Unify the real paths too, so C, C++, Foundation and the game see the same data.
#import <Foundation/Foundation.h>

static BOOL MergeMissing(NSString *source, NSString *target, NSError **error) {
    NSFileManager *fm = NSFileManager.defaultManager;
    NSArray *names = [fm contentsOfDirectoryAtPath:source error:error];
    if (!names) return NO;
    for (NSString *name in names) {
        NSString *src = [source stringByAppendingPathComponent:name];
        NSString *dst = [target stringByAppendingPathComponent:name];
        BOOL destinationDirectory = NO;
        BOOL exists = [fm fileExistsAtPath:dst isDirectory:&destinationDirectory] ||
                      [fm destinationOfSymbolicLinkAtPath:dst error:nil] != nil;
        if (!exists) {
            if (![fm copyItemAtPath:src toPath:dst error:error]) return NO;
        } else {
            NSDictionary *attributes = [fm attributesOfItemAtPath:src error:error];
            if (!attributes) return NO;
            if ([attributes[NSFileType] isEqualToString:NSFileTypeDirectory] && destinationDirectory &&
                ![fm destinationOfSymbolicLinkAtPath:dst error:nil]) {
                if (!MergeMissing(src, dst, error)) return NO;
            }
            // Conflicting files stay in the source directory, which is backed
            // up before aliasing. Never replace an existing destination file.
        }
    }
    return YES;
}
static BOOL PreparePathPair(NSString *native, NSString *visible) {
    NSFileManager *fm = NSFileManager.defaultManager;
    NSError *error = nil;
    if (![fm createDirectoryAtPath:visible withIntermediateDirectories:YES attributes:nil error:&error]) {
        NSLog(@"PORT0R canonical path failed %@: %@", visible, error); return NO;
    }
    NSString *link = [fm destinationOfSymbolicLinkAtPath:native error:nil];
    if (link) {
        BOOL correct = [[native stringByResolvingSymlinksInPath] isEqualToString:[visible stringByResolvingSymlinksInPath]];
        NSLog(@"PORT0R path alias %@ correct=%d", native, correct);
        return correct; // preserve unknown symlinks rather than following/moving them
    }
    NSString *backup = nil;
    BOOL directory = NO;
    if ([fm fileExistsAtPath:native isDirectory:&directory]) {
        if (!directory || !MergeMissing(native, visible, &error)) {
            NSLog(@"PORT0R path merge failed %@: %@", native, error); return NO;
        }
        backup = [native stringByAppendingString:@".before-ios-paths"];
        if ([fm fileExistsAtPath:backup]) backup = [backup stringByAppendingFormat:@"-%@", NSUUID.UUID.UUIDString];
        if (![fm moveItemAtPath:native toPath:backup error:&error]) {
            NSLog(@"PORT0R path backup failed %@: %@", native, error); return NO;
        }
    }
    [fm createDirectoryAtPath:native.stringByDeletingLastPathComponent withIntermediateDirectories:YES attributes:nil error:nil];
    if (![fm createSymbolicLinkAtPath:native withDestinationPath:visible error:&error]) {
        if (backup) [fm moveItemAtPath:backup toPath:native error:nil];
        NSLog(@"PORT0R path alias failed %@: %@", native, error); return NO;
    }
    NSLog(@"PORT0R path unified %@ -> %@ backup=%@", native, visible, backup ?: @"none");
    return YES;
}
__attribute__((visibility("default"))) void Port0rPreparePaths(void) {
    NSString *home = NSHomeDirectory();
    BOOL downloads = PreparePathPair([home stringByAppendingPathComponent:@"Downloads"],
                                     [home stringByAppendingPathComponent:@"Documents/Downloads"]);
    BOOL data = PreparePathPair([home stringByAppendingPathComponent:@"Library/Application Support/Port0r"],
                                [home stringByAppendingPathComponent:@"Documents/Port0r"]);
    NSLog(@"PORT0R import path status downloads=%d data=%d", downloads, data);
    for (NSString *file in @[@"srallyc.zip", @"segabill.zip"]) {
        NSString *path = [[home stringByAppendingPathComponent:@"Documents/Downloads"] stringByAppendingPathComponent:file];
        NSDictionary *attributes = [NSFileManager.defaultManager attributesOfItemAtPath:path error:nil];
        NSLog(@"PORT0R ROM candidate %@ present=%d bytes=%@", file, attributes != nil, attributes[NSFileSize] ?: @0);
    }
}
