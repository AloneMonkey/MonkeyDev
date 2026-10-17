#!/bin/bash
# Sourced by pack.sh. The proprietary SDK stays in the user's Reveal installation.
function integrateReveal() {
    [[ "${MONKEYDEV_REVEAL:-NO}" == YES ]] || return 0
    if [[ "${CONFIGURATION:-}" != Debug ]]; then
        echo "Reveal skipped: only Debug builds are supported."
        return 0
    fi
    [[ "${PLATFORM_NAME:-}" == iphoneos ]] || panic 1 "Reveal integration requires an iPhoneOS device build"
    local sdk="${MONKEYDEV_REVEAL_SDK:-${HOME}/Library/Application Support/Reveal/RevealServer/RevealServer.xcframework}"
    local index=0 platform variant identifier library arches selected=""
    [[ -f "$sdk/Info.plist" ]] || panic 1 "Reveal SDK not found: $sdk (install it from Reveal, or set MONKEYDEV_REVEAL_SDK)"
    while identifier=$(/usr/libexec/PlistBuddy -c "Print :AvailableLibraries:$index:LibraryIdentifier" "$sdk/Info.plist" 2>/dev/null); do
        platform=$(/usr/libexec/PlistBuddy -c "Print :AvailableLibraries:$index:SupportedPlatform" "$sdk/Info.plist" 2>/dev/null)
        variant=$(/usr/libexec/PlistBuddy -c "Print :AvailableLibraries:$index:SupportedPlatformVariant" "$sdk/Info.plist" 2>/dev/null || true)
        arches=$(/usr/libexec/PlistBuddy -c "Print :AvailableLibraries:$index:SupportedArchitectures" "$sdk/Info.plist" 2>/dev/null)
        if [[ "$platform" == ios && -z "$variant" ]] && /usr/bin/grep -qw arm64 <<< "$arches"; then
            library=$(/usr/libexec/PlistBuddy -c "Print :AvailableLibraries:$index:LibraryPath" "$sdk/Info.plist")
            selected="$sdk/$identifier/$library"
            break
        fi
        index=$((index + 1))
    done
    [[ -d "$selected" && -f "$selected/RevealServer" ]] || panic 1 "Reveal SDK has no iOS arm64 device framework"
    local destination="$BUILD_APP_PATH/Frameworks/RevealServer.framework"
    [[ ! -e "$destination" ]] || panic 1 "Input App already contains RevealServer.framework; remove that dependency before enabling MONKEYDEV_REVEAL"
    mkdir -p "$BUILD_APP_PATH/Frameworks" || panic 1 "Cannot create Frameworks directory"
    cp -R "$selected" "$destination" || panic 1 "Cannot copy Reveal framework"
    arches=$(/usr/bin/lipo -archs "$destination/RevealServer") || panic 1 "Cannot inspect Reveal binary"
    if [[ "$arches" != arm64 ]]; then
        /usr/bin/lipo "$destination/RevealServer" -thin arm64 -output "$destination/RevealServer.arm64" || panic 1 "Cannot extract Reveal arm64 slice"
        mv -f "$destination/RevealServer.arm64" "$destination/RevealServer" || panic 1 "Cannot replace Reveal binary"
    fi
    rm -rf "$destination/_CodeSignature" || panic 1 "Cannot remove old Reveal signature"
    "$MONKEYPARSER" install -c load -p '@executable_path/Frameworks/RevealServer.framework/RevealServer' -t "$BUILD_APP_PATH/$APP_BINARY" || panic 1 "Reveal injection failed"
    configureRevealDiscovery
    echo "Reveal integrated (Debug, arm64): $selected"
}

# Xcode can process the project's Info.plist after the packaging phase. Apply
# discovery metadata again in the final signing phase, before sealing the App.
function configureRevealDiscovery() {
    [[ "${MONKEYDEV_REVEAL:-NO}" == YES && "${CONFIGURATION:-}" == Debug ]] || return 0
    [[ "${PLATFORM_NAME:-}" == iphoneos ]] || panic 1 "Reveal integration requires an iPhoneOS device build"
    [[ -f "$BUILD_APP_PATH/Frameworks/RevealServer.framework/RevealServer" ]] || panic 1 "Reveal framework missing before final signing"
    local plist="$BUILD_APP_PATH/Info.plist" service count=0 found=NO
    /usr/libexec/PlistBuddy -c 'Print :NSBonjourServices' "$plist" >/dev/null 2>&1 || \
        /usr/libexec/PlistBuddy -c 'Add :NSBonjourServices array' "$plist" || panic 1 "Cannot create Bonjour services"
    while service=$(/usr/libexec/PlistBuddy -c "Print :NSBonjourServices:$count" "$plist" 2>/dev/null); do
        [[ "$service" != _reveal._tcp ]] || found=YES
        count=$((count + 1))
    done
    if [[ "$found" != YES ]]; then
        /usr/libexec/PlistBuddy -c 'Add :NSBonjourServices: string _reveal._tcp' "$plist" || panic 1 "Cannot add Reveal Bonjour service"
    fi
    /usr/libexec/PlistBuddy -c 'Print :NSLocalNetworkUsageDescription' "$plist" >/dev/null 2>&1 || \
        /usr/libexec/PlistBuddy -c 'Add :NSLocalNetworkUsageDescription string Allow Reveal on your Mac to inspect this debug app.' "$plist" || panic 1 "Cannot add local network description"
}
