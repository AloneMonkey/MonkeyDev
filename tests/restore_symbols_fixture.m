#import <Foundation/Foundation.h>

@interface MDRestoreFixture : NSObject
- (NSInteger)add:(NSInteger)value;
+ (NSString *)marker;
@end
@implementation MDRestoreFixture
- (NSInteger)add:(NSInteger)value { return value + 42; }
+ (NSString *)marker { return @"restore-symbol-marker"; }
@end

@interface MDRestoreFixture (Extra)
- (NSString *)categoryMarker;
@end
@implementation MDRestoreFixture (Extra)
- (NSString *)categoryMarker { return @"restore-category"; }
@end

@interface NSObject (MDRestoreExternal)
- (NSInteger)mdRestoreExternal;
@end
@implementation NSObject (MDRestoreExternal)
- (NSInteger)mdRestoreExternal { return 7; }
@end

int main(void) {
    @autoreleasepool {
        MDRestoreFixture *value = [MDRestoreFixture new];
        NSLog(@"%@ %@ %ld %ld", [MDRestoreFixture marker], [value categoryMarker],
              (long)[value add:1], (long)[value mdRestoreExternal]);
    }
    return 0;
}
