%config(generator=internal);
#import <Foundation/Foundation.h>
%hook MDHookChain
- (NSInteger)value {
    NSInteger original = %orig;
    return original + 10;
}
%end
