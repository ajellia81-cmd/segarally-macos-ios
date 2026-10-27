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
// Import explicitly: the desktop importer mixes search-path APIs, C++ filesystem
// and focus events which do not have identical behavior in LiveContainer.
static BOOL ImportDownloads(NSString *downloads, NSString *roms) {
    NSFileManager *fm = NSFileManager.defaultManager;
    NSError *error = nil;
    NSArray<NSString *> *names = [fm contentsOfDirectoryAtPath:downloads error:&error];
    if (!names) { NSLog(@"PORT0R Downloads scan failed %@: %@", downloads, error); return NO; }
    if (![fm createDirectoryAtPath:roms withIntermediateDirectories:YES attributes:nil error:&error]) return NO;
    BOOL ok = YES;
    for (NSString *wanted in @[@"srallyc.zip", @"segabill.zip"]) {
        NSString *match = nil;
        for (NSString *name in names) if ([name caseInsensitiveCompare:wanted] == NSOrderedSame) { match = name; break; }
        if (!match) { NSLog(@"PORT0R Downloads missing %@ at %@", wanted, downloads); continue; }
        NSString *source = [downloads stringByAppendingPathComponent:match];
        NSString *target = [roms stringByAppendingPathComponent:wanted];
        BOOL directory = NO;
        if (![fm fileExistsAtPath:source isDirectory:&directory] || directory) { ok = NO; continue; }
        NSFileHandle *handle = [NSFileHandle fileHandleForReadingAtPath:source];
        NSData *magic = [handle readDataOfLength:4]; [handle closeFile];
        const unsigned char *b = (const unsigned char *)magic.bytes;
        if (magic.length != 4 || b[0] != 'P' || b[1] != 'K' || b[2] != 3 || b[3] != 4) {
            NSLog(@"PORT0R Downloads rejected %@: not a ZIP local-file header", match); ok = NO; continue;
        }
        if ([fm contentsEqualAtPath:source andPath:target]) continue;
        NSString *temp = [roms stringByAppendingPathComponent:[@".import-" stringByAppendingString:NSUUID.UUID.UUIDString]];
        if (![fm copyItemAtPath:source toPath:temp error:&error]) {
            NSLog(@"PORT0R Downloads copy failed %@: %@", match, error); ok = NO; continue;
        }
        // Preserve a prior ROM before replacing; never touch the source archive.
        if ([fm fileExistsAtPath:target]) {
            NSString *backup = [target stringByAppendingFormat:@".before-import-%@", NSUUID.UUID.UUIDString];
            if (![fm moveItemAtPath:target toPath:backup error:&error]) {
                [fm removeItemAtPath:temp error:nil]; ok = NO; continue;
            }
            if (![fm moveItemAtPath:temp toPath:target error:&error]) {
                [fm moveItemAtPath:backup toPath:target error:nil];
                [fm removeItemAtPath:temp error:nil]; ok = NO; continue;
            }
        } else if (![fm moveItemAtPath:temp toPath:target error:&error]) {
            [fm removeItemAtPath:temp error:nil]; ok = NO; continue;
        }
        NSLog(@"PORT0R Downloads imported %@ -> %@ bytes=%@", source, target,
              [fm attributesOfItemAtPath:target error:nil][NSFileSize]);
    }
    return ok;
}
__attribute__((visibility("default"))) void Port0rImportDownloads(void) {
    NSString *home = NSHomeDirectory();
    ImportDownloads([home stringByAppendingPathComponent:@"Documents/Downloads"],
                    [home stringByAppendingPathComponent:@"Documents/Port0r/srallyc/roms"]);
}
__attribute__((visibility("default"))) void Port0rPreparePaths(void) {
    NSString *home = NSHomeDirectory();
    BOOL downloads = PreparePathPair([home stringByAppendingPathComponent:@"Downloads"],
                                     [home stringByAppendingPathComponent:@"Documents/Downloads"]);
    BOOL data = PreparePathPair([home stringByAppendingPathComponent:@"Library/Application Support/Port0r"],
                                [home stringByAppendingPathComponent:@"Documents/Port0r"]);
    NSLog(@"PORT0R import path status downloads=%d data=%d", downloads, data);
    Port0rImportDownloads();
}
