#import <Foundation/Foundation.h>
long mdRuntimeIvarOffset;
@protocol MDHeaderProtocol <NSObject>
- (NSInteger)calculate:(NSInteger)value;
@optional
- (void)optionalMarker;
@end
@interface MDHeaderFixture : NSObject <MDHeaderProtocol> {
    NSInteger _counter;
}
@property(nonatomic, copy) NSString *title;
+ (NSString *)marker;
@end
@implementation MDHeaderFixture
- (NSInteger)calculate:(NSInteger)value { return value + _counter; }
+ (NSString *)marker { return @"header-fixture"; }
@end
@interface NSObject (MDHeaderExternal)
- (NSInteger)mdHeaderExternal;
@end
@implementation NSObject (MDHeaderExternal)
- (NSInteger)mdHeaderExternal { return 7; }
@end
int main(void) {
    @autoreleasepool {
        MDHeaderFixture *value = [MDHeaderFixture new];
        value.title = @"example";
        NSLog(@"%@ %ld", value.title, (long)[value calculate:1]);
    }
    return 0;
}
