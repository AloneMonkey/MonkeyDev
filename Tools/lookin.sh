#!/bin/bash
# Sourced by pack.sh. The default arm64 LookinServer SDK ships with MonkeyDev.
function integrateLookin() {
    [[ "${MONKEYDEV_UI_INSPECTOR:-}" == Lookin ]] || return 0
    if [[ "${CONFIGURATION:-}" != Debug ]]; then
        echo 'Lookin skipped: only Debug builds are supported.'
        return 0
    fi
    [[ "${PLATFORM_NAME:-}" == iphoneos ]] || panic 1 'Lookin integration requires an iPhoneOS device build'
    local sdk="${MONKEYDEV_LOOKIN_SDK:-$MONKEYDEV_PATH/Librarys/Lookin/LookinServer.framework}"
    [[ -f "$sdk/Info.plist" && -f "$sdk/LookinServer" ]] || panic 1 "LookinServer SDK not found: $sdk. Reinstall/update MonkeyDev or set MONKEYDEV_LOOKIN_SDK to a dynamic framework."
    local version arches description
    version=$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$sdk/Info.plist") || panic 1 'Cannot read LookinServer version'
    # The upstream explicitly excludes versions earlier than 1.0.6.
    /usr/bin/awk -v v="$version" 'BEGIN { n=split(v,a,"."); exit !(n>=3 && (a[1]>1 || (a[1]==1 && (a[2]>0 || (a[2]==0 && a[3]>=6))))) }' || panic 1 'LookinServer 1.0.6 or newer is required'
    arches=$(/usr/bin/lipo -archs "$sdk/LookinServer") || panic 1 'Cannot inspect LookinServer binary'
    /usr/bin/grep -qw arm64 <<< "$arches" || panic 1 'LookinServer SDK requires an arm64 device slice'
    local destination="$BUILD_APP_PATH/Frameworks/LookinServer.framework"
    [[ ! -e "$destination" ]] || panic 1 'Input App already contains LookinServer.framework; disable the inspector or remove that dependency first'
    mkdir -p "$BUILD_APP_PATH/Frameworks" || panic 1 'Cannot create Frameworks directory'
    cp -R "$sdk" "$destination" || panic 1 'Cannot copy LookinServer SDK'
    if [[ "$arches" != arm64 ]]; then
        /usr/bin/lipo "$destination/LookinServer" -thin arm64 -output "$destination/LookinServer.arm64" || panic 1 'Cannot extract LookinServer arm64 slice'
        mv -f "$destination/LookinServer.arm64" "$destination/LookinServer" || panic 1 'Cannot replace LookinServer binary'
    fi
    description=$(/usr/bin/otool -hv "$destination/LookinServer") || panic 1 'Cannot inspect LookinServer Mach-O type'
    [[ "$description" == *DYLIB* ]] || panic 1 'LookinServer must be a dynamic framework, not a static library'
    description=$(/usr/bin/otool -l "$destination/LookinServer") || panic 1 'Cannot inspect LookinServer platform'
    if [[ "$description" == *LC_BUILD_VERSION* ]]; then
        /usr/bin/grep -Eq 'platform[[:space:]]+2$' <<< "$description" || panic 1 'LookinServer must target iOS devices, not the simulator'
    else
        [[ "$description" == *LC_VERSION_MIN_IPHONEOS* ]] || panic 1 'LookinServer must target iOS devices'
    fi
    rm -rf "$destination/_CodeSignature" || panic 1 'Cannot remove old LookinServer signature'
    "$MONKEYPARSER" install -c load -p '@executable_path/Frameworks/LookinServer.framework/LookinServer' -t "$BUILD_APP_PATH/$APP_BINARY" || panic 1 'Lookin injection failed'
    echo "Lookin integrated (Debug, arm64, USB): $sdk"
}
