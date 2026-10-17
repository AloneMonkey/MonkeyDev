#import <Foundation/Foundation.h>
#import <CaptainHook/CaptainHook.h>
#include <math.h>
#import <dispatch/dispatch.h>

#ifdef CHUseSubstrate
#error This fixture must use CaptainHook's internal backend.
#endif

typedef struct { double a, b, c, d; } MDHookQuad;
@interface MDHookBase : NSObject
- (NSInteger)number:(NSInteger)value;
- (NSString *)echo:(NSString *)value;
- (double)scale:(double)value ratio:(double)ratio;
- (MDHookQuad)quad:(MDHookQuad)value;
+ (NSString *)marker;
@end
@implementation MDHookBase
- (NSInteger)number:(NSInteger)value { return value + 3; }
- (NSString *)echo:(NSString *)value { return [value stringByAppendingString:@"-original"]; }
- (double)scale:(double)value ratio:(double)ratio { return value * ratio; }
- (MDHookQuad)quad:(MDHookQuad)value { value.a += 1; return value; }
+ (NSString *)marker { return @"original"; }
@end
@interface MDHookChild : MDHookBase @end
@implementation MDHookChild @end
@interface MDHookSibling : MDHookBase @end
@implementation MDHookSibling @end
@interface MDHookChain : NSObject
- (NSInteger)value;
@end
@implementation MDHookChain
- (NSInteger)value { return 4; }
@end

CHDeclareClass(MDHookBase);
CHDeclareClass(MDHookChild);
CHDeclareClass(MDHookChain);
CHMethod1(NSInteger, MDHookChild, number, NSInteger, value) {
    return CHSuper1(MDHookChild, number, value) + 10;
}
CHMethod1(NSString *, MDHookBase, echo, NSString *, value) {
    return [CHSuper1(MDHookBase, echo, value) stringByAppendingString:@"-hook"];
}
CHMethod2(double, MDHookBase, scale, double, value, ratio, double, ratio) {
    return CHSuper2(MDHookBase, scale, value, ratio, ratio) + 0.5;
}
CHMethod1(MDHookQuad, MDHookBase, quad, MDHookQuad, value) {
    MDHookQuad result = CHSuper1(MDHookBase, quad, value);
    result.d += 2; return result;
}
CHClassMethod0(NSString *, MDHookBase, marker) {
    return [CHSuper0(MDHookBase, marker) stringByAppendingString:@"-classhook"];
}
CHMethod0(NSInteger, MDHookChain, value) {
    return CHSuper0(MDHookChain, value) + 3;
}

#define MD_REQUIRE(condition) do { if (!(condition)) { NSLog(@"[MonkeyDevCaptainHook] FAIL line %d", __LINE__); return NO; } } while (0)
static BOOL runCaptainHookChecks(void) {
    CHLoadClass(MDHookBase); CHLoadClass(MDHookChild); CHLoadClass(MDHookChain);
    CHHook1(MDHookChild, number);
    CHHook1(MDHookBase, echo);
    CHHook2(MDHookBase, scale, ratio);
    CHHook1(MDHookBase, quad);
    CHClassHook0(MDHookBase, marker);
    CHHook0(MDHookChain, value);
    MDHookBase *base = [MDHookBase new];
    MD_REQUIRE([base number:2] == 5);
    MD_REQUIRE([[MDHookChild new] number:2] == 15);
    MD_REQUIRE([[MDHookSibling new] number:2] == 5);
    MD_REQUIRE([[base echo:@"input"] isEqualToString:@"input-original-hook"]);
    MD_REQUIRE(fabs([base scale:2.5 ratio:4] - 10.5) < 0.0001);
    MDHookQuad q = [base quad:(MDHookQuad){1,2,3,4}];
    MD_REQUIRE(q.a == 2 && q.b == 2 && q.c == 3 && q.d == 6);
    MD_REQUIRE([[MDHookBase marker] isEqualToString:@"original-classhook"]);
#ifdef MD_CAPTAIN_LOGOS_TEST
    MD_REQUIRE([[MDHookChain new] value] == 17);
#else
    MD_REQUIRE([[MDHookChain new] value] == 7);
#endif
    NSLog(@"[MonkeyDevCaptainHook] PASS: instance/class methods, inheritance, object/float/struct ABI, original calls");
    return YES;
}
#ifdef MD_CAPTAIN_DEVICE_TEST
__attribute__((constructor)) static void captainHookDeviceChecks(void) {
    dispatch_async(dispatch_get_main_queue(), ^{ @autoreleasepool { runCaptainHookChecks(); } });
}
#else
int main(void) { @autoreleasepool { return runCaptainHookChecks() ? 0 : 1; } }
#endif
