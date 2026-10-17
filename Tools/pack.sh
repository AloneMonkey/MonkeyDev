#!/bin/bash

MONKEYDEV_PATH="${MonkeyDevPath:-/opt/MonkeyDev}"

# temp path
TEMP_PATH="${TARGET_TEMP_DIR:-${TARGET_BUILD_DIR:-${BUILT_PRODUCTS_DIR}}}/.monkeydev-input-${TARGET_NAME}"

# monkeyparser
MONKEYPARSER="${MONKEYDEV_MONKEYPARSER:-${MONKEYDEV_PATH}/bin/monkeyparser}"
CLASS_DUMP="${MONKEYDEV_CLASS_DUMP_TOOL:-${MONKEYDEV_PATH}/bin/class-dump}"

# create ipa script
CREATE_IPA="${MONKEYDEV_PATH}/bin/createIPA.command"

# build app path
BUILD_APP_PATH="${TARGET_BUILD_DIR:-${BUILT_PRODUCTS_DIR}}/${FULL_PRODUCT_NAME:-${TARGET_NAME}.app}"

# default demo app
DEMOTARGET_APP_PATH="${MONKEYDEV_PATH}/Resource/TargetApp.app"

# link framework path
FRAMEWORKS_TO_INJECT_PATH="${MONKEYDEV_PATH}/Frameworks/"

# target app placed
TARGET_APP_PUT_PATH="${SRCROOT}/${TARGET_NAME}/TargetApp"

# Compatiable old version
MONKEYDEV_INSERT_DYLIB=${MONKEYDEV_INSERT_DYLIB:=YES}
MONKEYDEV_TARGET_APP=${MONKEYDEV_TARGET_APP:=Optional}
if [[ "${MONKEYDEV_ADD_SUBSTRATE:-}" == "YES" ]]; then
	echo "WARNING: MONKEYDEV_ADD_SUBSTRATE is obsolete. MonkeyDev no longer bundles Substrate; use CaptainHook/Logos internal or supply your own runtime." >&2
fi
MONKEYDEV_DEFAULT_BUNDLEID=${MONKEYDEV_DEFAULT_BUNDLEID:=NO}

function isRelease() {
	if [[ "${CONFIGURATION}" = "Release" ]]; then
		true
	else
		false
	fi
}

function panic() { # args: exitCode, message...
	local exitCode=$1
	set +e
	
	shift
	[[ "$@" == "" ]] || \
		echo "$@" >&2

	exit ${exitCode}
}

function removeDeviceRestriction() {
	local plist="$1"
	if /usr/libexec/PlistBuddy -c 'Print :UISupportedDevices' "$plist" >/dev/null 2>&1; then
		/usr/libexec/PlistBuddy -c 'Delete :UISupportedDevices' "$plist" || panic 1 "Cannot remove input device restriction"
	fi
}

function checkApp(){
	local TARGET_APP_PATH="$1"
	local sourceApp="${2:-}"
	if [[ -n "$sourceApp" && ! -e "$sourceApp/.monkeydev-signing-input" ]]; then
		rm -f "$TARGET_APP_PATH/.monkeydev-signing-input" || panic 1 "Cannot remove obsolete signing marker"
	fi
	# Clean a previously auto-copied library before verify sees its old fat slices.
	# Libraries actually supplied by the input App remain part of that App.
	if [[ -n "$sourceApp" && ! -e "$sourceApp/Frameworks/libsubstrate.dylib" ]]; then
		rm -f "$TARGET_APP_PATH/Frameworks/libsubstrate.dylib" || panic 1 "Cannot remove stale Substrate runtime"
	fi
	if [[ -n "$sourceApp" && ! -e "$sourceApp/Frameworks/RevealServer.framework" ]]; then
		rm -rf "$TARGET_APP_PATH/Frameworks/RevealServer.framework" || panic 1 "Cannot remove stale Reveal framework"
	fi
	# Drop files left by old MonkeyDev builds, preserving input-owned libraries.
	local retired
	for retired in libcycript.dylib libcycript.cy libcycript.db; do
		if [[ -n "$sourceApp" && ! -e "$sourceApp/Frameworks/$retired" ]]; then
			rm -f "$TARGET_APP_PATH/Frameworks/$retired" || panic 1 "Cannot remove stale Cycript file: $retired"
		fi
	done

	# remove Plugin an Watch
	rm -rf "${TARGET_APP_PATH}/PlugIns" || true
	rm -rf "${TARGET_APP_PATH}/Watch" || true
	# The App Store manifest still lists removed extensions in SinfReplicationPaths.
	# Keeping it makes later installs inspect nonexistent PlugIns/*.appex bundles.
	# This is the verified, decrypted build copy; the original input stays intact.
	rm -rf "${TARGET_APP_PATH}/SC_Info" || panic 1 "Failed to remove stale App Store metadata"

	removeDeviceRestriction "${TARGET_APP_PATH}/Info.plist"

	# Verification stays read-only; restoration is a separate checked transform.
	VERIFY_RESULT=$(MONKEYDEV_CLASS_DUMP=NO MONKEYDEV_RESTORE_SYMBOL=NO "$MONKEYPARSER" verify -t "${TARGET_APP_PATH}" -o "${SRCROOT}/${TARGET_NAME}") || \
		panic 1 "${VERIFY_RESULT}"
	echo "${VERIFY_RESULT}"
	if [[ "${MONKEYDEV_RESTORE_SYMBOL}" == "YES" || "${MONKEYDEV_CLASS_DUMP}" == "YES" ]]; then
		local restoreExecutable
		restoreExecutable=$(/usr/libexec/PlistBuddy -c 'Print :CFBundleExecutable' "${TARGET_APP_PATH}/Info.plist") || panic 1 "Cannot read executable for symbol restoration"
		[[ -n "$restoreExecutable" && "$restoreExecutable" != */* && "$restoreExecutable" != . && "$restoreExecutable" != .. ]] || panic 1 "Invalid executable name for symbol restoration"
		if [[ "${MONKEYDEV_CLASS_DUMP}" == "YES" ]]; then
			local headersParent="${PROJECT_DIR:-${SRCROOT}}/Headers"
			local headersOutput="${headersParent}/${TARGET_NAME}" headersStage headersBackup
			[[ -x "$CLASS_DUMP" ]] || panic 1 "Missing class-dump: $CLASS_DUMP"
			mkdir -p "$headersParent" || panic 1 "Cannot create header output directory"
			headersStage=$(mktemp -d "${headersParent}/.dump.XXXXXX") || panic 1 "Cannot stage class-dump output"
			if ! "$CLASS_DUMP" --arch arm64 -H -o "$headersStage" "${TARGET_APP_PATH}/${restoreExecutable}"; then
				rm -rf "$headersStage"
				panic 1 "Objective-C header export failed; previous headers kept"
			fi
			headersBackup="${headersStage}.previous"
			if [[ -e "$headersOutput" ]]; then
				mv "$headersOutput" "$headersBackup" || panic 1 "Cannot preserve previous headers"
			fi
			if ! mv "$headersStage" "$headersOutput"; then
				[[ ! -e "$headersBackup" ]] || mv "$headersBackup" "$headersOutput"
				panic 1 "Cannot publish exported headers"
			fi
			rm -rf "$headersBackup"
			echo "Objective-C headers: $headersOutput"
		fi
		if [[ "${MONKEYDEV_RESTORE_SYMBOL}" == "YES" ]]; then
			"$MONKEYPARSER" restoresymbol -t "${TARGET_APP_PATH}/${restoreExecutable}" || panic 1 "Objective-C symbol restoration failed"
		fi
	fi
}

# Legacy optional frameworks can still be requested, but never copy the retired
# Substrate binary from an older installation into a new build.
function copyOptionalFrameworks() {
	local destination="$1" item
	for item in "${FRAMEWORKS_TO_INJECT_PATH}"*; do
		[[ -e "$item" ]] || continue
		[[ "${item##*/}" != libsubstrate.dylib && "${item##*/}" != RevealServer.framework ]] || continue
		case "${item##*/}" in libcycript.*) continue ;; esac
		cp -Rf "$item" "$destination/" || panic 1 "Cannot copy optional framework: $item"
	done
}

# Never merge a new input into a previous repacked App: removed libraries and
# resources would survive. Stage the input before touching the existing product.
function replaceBuildApp() {
	local input="$1" stage
	[[ -d "$input" && -f "$input/Info.plist" ]] || panic 1 "Input App is missing or incomplete: $input"
	[[ -n "$BUILD_APP_PATH" && "$BUILD_APP_PATH" == /*.app && ! -L "$BUILD_APP_PATH" ]] || panic 1 "Invalid built App path: $BUILD_APP_PATH"
	[[ ! "$input" -ef "$BUILD_APP_PATH" ]] || panic 1 "Input App must differ from the build product"
	# Keep full bundle copies outside source groups. Xcode synchronized groups
	# otherwise observe thousands of transient files and can crash while scanning.
	repackWork=$(mktemp -d "${BUILD_APP_PATH%/*}/.monkeydev-repack.XXXXXX") || panic 1 "Cannot stage input App"
	stage="$repackWork/input.app"
	mkdir "$stage" || panic 1 "Cannot create staged App"
	cp -pR "$input/." "$stage/" || { rm -rf "$repackWork"; panic 1 "Cannot copy input App"; }
	# Xcode's profile takes precedence over the profile carried by the input App.
	if [[ -f "$BUILD_APP_PATH/embedded.mobileprovision" ]]; then
		cp -p "$BUILD_APP_PATH/embedded.mobileprovision" "$stage/embedded.mobileprovision" || panic 1 "Cannot preserve Xcode provisioning profile"
	fi
	previousBuildApp="$repackWork/previous.app"
	if [[ -e "$BUILD_APP_PATH" ]]; then
		mv "$BUILD_APP_PATH" "$previousBuildApp" || panic 1 "Cannot preserve previous App product"
	fi
	# Restore the previous product if a checked packaging step fails.
	trap rollbackBuildApp EXIT
	mv "$stage" "$BUILD_APP_PATH" || panic 1 "Cannot publish fresh App product"
}

function rollbackBuildApp() {
	local result=$?
	trap - EXIT
	if ! rm -rf "$BUILD_APP_PATH" || { [[ -d "$previousBuildApp" ]] && ! mv "$previousBuildApp" "$BUILD_APP_PATH"; }; then
		echo "ERROR: Cannot restore previous App; recovery files kept at $repackWork" >&2
		exit 1
	fi
	rm -rf "$repackWork"
	if [[ "${inputCacheActive:-}" == YES ]]; then rm -rf "$TEMP_PATH"; fi
	exit "$result"
}

# Xcode may skip unchanged Resources/CopyFiles tasks on incremental builds.
# Carry over only files outside the previous pack manifest. Snapshot this pack's
# files BEFORE that merge so Xcode-owned outputs keep their ownership next time.
function finishBuildApp() {
	local stateDir="${TARGET_TEMP_DIR:-${BUILT_PRODUCTS_DIR}}"
	mkdir -p "$stateDir" || panic 1 "Cannot create packaging state directory"
	/usr/bin/perl - "$previousBuildApp" "$BUILD_APP_PATH" "$stateDir/.monkeydev-${TARGET_NAME}.pack-files" <<'PERL' || panic 1 "Cannot preserve Xcode build outputs"
use strict;
use warnings;
use File::Find;
use File::Basename qw(dirname);
use File::Path qw(make_path);
use File::Copy qw(copy);
use File::Temp qw(tempfile);
my ($old, $app, $manifest) = @ARGV;
my (%managed, @current);
my $has_previous = -f $manifest;
if ($has_previous) {
    open my $fh, '<', $manifest or die "read manifest: $!";
    local $/ = "\0";
    while (my $path = <$fh>) { chomp $path; $managed{$path} = 1; }
    close $fh or die "close manifest: $!";
}
find({no_chdir => 1, wanted => sub {
    push @current, substr($File::Find::name, length($app) + 1) if -f $_ || -l $_;
}}, $app);
if ($has_previous && -d $old) {
    find({no_chdir => 1, wanted => sub {
        return unless -f $_ || -l $_;
        my $relative = substr($File::Find::name, length($old) + 1);
        return if $managed{$relative} || $relative =~ m{(?:^|/)_CodeSignature(?:/|$)};
        my $destination = "$app/$relative";
        return if -e $destination || -l $destination;
        my $parent = dirname($destination);
        for (my $path = $parent; length($path) > length($app); $path = dirname($path)) {
            die "symlink in output path: $path" if -l $path;
        }
        make_path($parent);
        if (-l $_) {
            symlink(readlink($_), $destination) or die "copy symlink $_: $!";
        } else {
            copy($_, $destination) or die "copy $_: $!";
            chmod((stat($_))[2] & 0777, $destination) or die "chmod $destination: $!";
        }
    }}, $old);
}
my ($fh, $temporary) = tempfile('.monkeydev-pack.XXXXXX', DIR => dirname($manifest), UNLINK => 1);
print {$fh} map { "$_\0" } sort @current;
close $fh or die "write manifest: $!";
rename($temporary, $manifest) or die "publish manifest: $!";
PERL
	trap - EXIT
	rm -rf "$repackWork" || panic 1 "Cannot clean previous App product"
	# Do not leave an unmodified input App next to the product: createIPA scans
	# the product directory for App bundles when exporting the signed build.
	rm -rf "$TEMP_PATH" || panic 1 "Cannot clean input cache"
}

function pack(){
	local injectedDylib="${BUILT_PRODUCTS_DIR}/lib${TARGET_NAME}Dylib.dylib"
	if [[ ${MONKEYDEV_INSERT_DYLIB} == YES ]]; then
		[[ -f "$injectedDylib" ]] || panic 1 "Project dylib not found: $injectedDylib"
	fi
	TARGET_INFO_PLIST=${SRCROOT}/${TARGET_NAME}/Info.plist
	# environment
	CURRENT_EXECUTABLE=$(/usr/libexec/PlistBuddy -c "Print CFBundleExecutable" "${TARGET_INFO_PLIST}" 2>/dev/null)

	# create tmp dir
	rm -rf "${TEMP_PATH}" || panic 1 "Cannot clear input cache"
	mkdir -p "${TEMP_PATH}" || panic 1 "Cannot create input cache"
	inputCacheActive=YES

	# latestbuild
	ln -fhs "${BUILT_PRODUCTS_DIR}" "${PROJECT_DIR}"/LatestBuild
	cp -rf "${CREATE_IPA}" "${PROJECT_DIR}"/LatestBuild/

	# deal ipa or app
	# Ignore the legacy source-tree extraction cache. IPA input takes precedence
	# over a previously extracted App and is unpacked fresh on every build.
	TARGET_APP_PATH=$(find "${SRCROOT}/${TARGET_NAME}" -path "${SRCROOT}/${TARGET_NAME}/tmp" -prune -o -type d -name '*.app' -print -prune | head -n 1)
	TARGET_IPA_PATH=$(find "${SRCROOT}/${TARGET_NAME}" -path "${SRCROOT}/${TARGET_NAME}/tmp" -prune -o -type d -name '*.app' -prune -o -type f -name '*.ipa' -print | head -n 1)
	if [[ -n "${MONKEYDEV_INPUT_APP}" ]]; then
		[[ -d "$MONKEYDEV_INPUT_APP" && "$MONKEYDEV_INPUT_APP" == *.app ]] || panic 1 "MONKEYDEV_INPUT_APP must point to an App bundle"
		TARGET_APP_PATH="$MONKEYDEV_INPUT_APP"
	fi

	if [[ ! ${TARGET_APP_PATH} ]] && [[ ! ${TARGET_IPA_PATH} ]] && [[ ${MONKEYDEV_TARGET_APP} != "Optional" ]]; then
		echo "pulling decrypted ipa from jailbreak device......."
		PYTHONIOENCODING=utf-8 ${MONKEYDEV_PATH}/bin/dump.py ${MONKEYDEV_TARGET_APP} -o "${TARGET_APP_PUT_PATH}/TargetApp.ipa" || panic 1 "dump.py error"
		TARGET_IPA_PATH=$(find "${TARGET_APP_PUT_PATH}" -type f | grep "\.ipa$" | head -n 1)
	fi

	if [[ -n "${TARGET_IPA_PATH}" && -z "${MONKEYDEV_INPUT_APP}" ]]; then
		unzip -oqq "${TARGET_IPA_PATH}" -d "${TEMP_PATH}" || { rm -rf "$TEMP_PATH"; panic 1 "Cannot extract input IPA: $TARGET_IPA_PATH"; }
		local inputApps=("${TEMP_PATH}/Payload/"*.app)
		[[ ${#inputApps[@]} == 1 && -d "${inputApps[0]}" ]] || { rm -rf "$TEMP_PATH"; panic 1 "Input IPA must contain exactly one Payload App"; }
		TARGET_APP_PATH="${inputApps[0]}"
	fi

	COPY_APP_PATH=${TARGET_APP_PATH}
	if [[ "${TARGET_APP_PATH}" = "" ]]; then
		COPY_APP_PATH=${DEMOTARGET_APP_PATH}
	fi
	replaceBuildApp "$COPY_APP_PATH"
	checkApp "${BUILD_APP_PATH}" "${COPY_APP_PATH}"

	# get target info
	ORIGIN_BUNDLE_ID=$(/usr/libexec/PlistBuddy -c "Print CFBundleIdentifier"  "${COPY_APP_PATH}/Info.plist" 2>/dev/null)
	TARGET_EXECUTABLE=$(/usr/libexec/PlistBuddy -c "Print CFBundleExecutable"  "${COPY_APP_PATH}/Info.plist" 2>/dev/null)

	if [[ ${CURRENT_EXECUTABLE} != ${TARGET_EXECUTABLE} ]]; then
		cp -rf "${COPY_APP_PATH}/Info.plist" "${TARGET_INFO_PLIST}"
	fi

	TARGET_DISPLAY_NAME=$(/usr/libexec/PlistBuddy -c "Print CFBundleDisplayName" "${TARGET_INFO_PLIST}" 2>/dev/null)

	# copy default framewrok
	TARGET_APP_FRAMEWORKS_PATH="${BUILD_APP_PATH}/Frameworks/"

	if [ ! -d "${TARGET_APP_FRAMEWORKS_PATH}" ]; then
		mkdir -p "${TARGET_APP_FRAMEWORKS_PATH}"
	fi

	if [[ ${MONKEYDEV_INSERT_DYLIB} == "YES" ]];then
		cp -f "$injectedDylib" "$TARGET_APP_FRAMEWORKS_PATH" || panic 1 "Cannot copy project dylib: $injectedDylib"
		if [[ "${MONKEYDEV_MINIMAL}" != "YES" ]]; then
			copyOptionalFrameworks "${TARGET_APP_FRAMEWORKS_PATH}"
		fi
		if isRelease; then
			rm -rf "${TARGET_APP_FRAMEWORKS_PATH}"/RevealServer.framework
		fi
	fi

	if [[ -d "$SRCROOT/${TARGET_NAME}/Resources" ]]; then
	 for file in "$SRCROOT/${TARGET_NAME}/Resources"/*; do
	 	extension="${file#*.}"
	  	filename="${file##*/}"
	  	if [[ "$extension" == "storyboard" ]]; then
	  		ibtool --compile "${BUILD_APP_PATH}/$filename"c "$file"
	  	else
	  		cp -rf "$file" "${BUILD_APP_PATH}/"
	  	fi
	 done
	fi

	# Inject the Dynamic Lib
	APP_BINARY=$(/usr/libexec/PlistBuddy -c 'Print :CFBundleExecutable' "${BUILD_APP_PATH}/Info.plist") || panic 1 "Cannot read the target executable"

	if [[ ${MONKEYDEV_INSERT_DYLIB} == "YES" ]];then
		"$MONKEYPARSER" install -c load -p "@executable_path/Frameworks/lib""${TARGET_NAME}""Dylib.dylib" -t "${BUILD_APP_PATH}/${APP_BINARY}" || panic 1 "Dylib injection failed"
		if [[ "${MONKEYDEV_MINIMAL}" != "YES" ]]; then
			"$MONKEYPARSER" unrestrict -t "${BUILD_APP_PATH}/${APP_BINARY}" || panic 1 "Failed to update restrict section"
		fi

		chmod +x "${BUILD_APP_PATH}/${APP_BINARY}"
	fi

	# Update Info.plist for Target App
	if [[ "${TARGET_DISPLAY_NAME}" != "" ]]; then
		for file in `ls "${BUILD_APP_PATH}"`;
		do
			extension="${file#*.}"
		    if [[ -d "${BUILD_APP_PATH}/$file" ]]; then
				if [[ "${extension}" == "lproj" ]]; then
					if [[ -f "${BUILD_APP_PATH}/${file}/InfoPlist.strings" ]];then
						/usr/libexec/PlistBuddy -c "Set :CFBundleDisplayName ${TARGET_DISPLAY_NAME}" "${BUILD_APP_PATH}/${file}/InfoPlist.strings"
					fi
		    	fi
			fi
		done
	fi

	if [[ ${MONKEYDEV_DEFAULT_BUNDLEID} = NO ]];then 
		/usr/libexec/PlistBuddy -c "Set :CFBundleIdentifier ${PRODUCT_BUNDLE_IDENTIFIER}" "${TARGET_INFO_PLIST}"
	else
		/usr/libexec/PlistBuddy -c "Set :CFBundleIdentifier ${ORIGIN_BUNDLE_ID}" "${TARGET_INFO_PLIST}"
	fi

	/usr/libexec/PlistBuddy -c "Delete :CFBundleIconFiles" "${TARGET_INFO_PLIST}"
	/usr/libexec/PlistBuddy -c "Add :CFBundleIconFiles array" "${TARGET_INFO_PLIST}"
	/usr/libexec/PlistBuddy -c "Add :CFBundleIconFiles: string ${TARGET_NAME}/icon.png" "${TARGET_INFO_PLIST}"

	cp -rf "${TARGET_INFO_PLIST}" "${BUILD_APP_PATH}/Info.plist"
	removeDeviceRestriction "${BUILD_APP_PATH}/Info.plist"

	#cocoapods
	if [[ -f "${SRCROOT}/Pods/Target Support Files/Pods-""${TARGET_NAME}""Dylib/Pods-""${TARGET_NAME}""Dylib-frameworks.sh" ]]; then
		source "${SRCROOT}/Pods/Target Support Files/Pods-""${TARGET_NAME}""Dylib/Pods-""${TARGET_NAME}""Dylib-frameworks.sh"
	fi

	if [[ -f "${SRCROOT}/Pods/Target Support Files/Pods-""${TARGET_NAME}""Dylib/Pods-""${TARGET_NAME}""Dylib-resources.sh" ]]; then
		source "${SRCROOT}/Pods/Target Support Files/Pods-""${TARGET_NAME}""Dylib/Pods-""${TARGET_NAME}""Dylib-resources.sh"
	fi

	if [[ -f "${SRCROOT}/../Pods/Target Support Files/Pods-""${TARGET_NAME}""Dylib/Pods-""${TARGET_NAME}""Dylib-frameworks.sh" ]]; then
		source "${SRCROOT}/../Pods/Target Support Files/Pods-""${TARGET_NAME}""Dylib/Pods-""${TARGET_NAME}""Dylib-frameworks.sh"
	fi

	if [[ -f "${SRCROOT}/../Pods/Target Support Files/Pods-""${TARGET_NAME}""Dylib/Pods-""${TARGET_NAME}""Dylib-resources.sh" ]]; then
		source "${SRCROOT}/../Pods/Target Support Files/Pods-""${TARGET_NAME}""Dylib/Pods-""${TARGET_NAME}""Dylib-resources.sh"
	fi

	# Integrate the user's current SDK into the build copy before embedded signing.
	source "${MONKEYDEV_PATH}/Tools/reveal.sh" || panic 1 "Cannot load Reveal integration"
	integrateReveal
	finishBuildApp
}

function signMainApp() {
    [[ "${CODE_SIGNING_ALLOWED}" != NO ]] || return 0
    # Standalone embedded-signing tests/callers do not provide an Xcode App context.
    [[ -n "${TARGET_TEMP_DIR:-}" && "${FULL_PRODUCT_NAME:-}" == *.app ]] || return 0
    local entitlements="$TARGET_TEMP_DIR/$FULL_PRODUCT_NAME.xcent"
    [[ -f "$entitlements" ]] || panic 1 "Xcode-generated signing entitlements not found: $entitlements"
    # Use exactly Xcode's processed entitlements and identity, never invent them.
    # This script is unconditional; native CodeSign may still run afterwards.
    /usr/bin/codesign --force --sign "$EXPANDED_CODE_SIGN_IDENTITY" --entitlements "$entitlements" --timestamp=none --generate-entitlement-der "$BUILD_APP_PATH" || panic 1 "Failed to sign repacked App"
}

function signEmbeddedCode() {
	# Sign nested code before sealing the repacked App. Xcode supplies the
	# provisioning profile, processed entitlements and signing identity.
	if [[ "${CODE_SIGNING_ALLOWED}" == "NO" ]]; then
		echo "Skipping embedded signing (CODE_SIGNING_ALLOWED=NO)"
		return
	fi
	[[ -n "${EXPANDED_CODE_SIGN_IDENTITY}" ]] || panic 1 "Xcode did not supply EXPANDED_CODE_SIGN_IDENTITY. Configure Signing & Capabilities."
	[[ -d "${BUILD_APP_PATH}" ]] || panic 1 "Built App not found: ${BUILD_APP_PATH}"
	local frameworkRoot="${BUILD_APP_PATH}/Frameworks"
	[[ -d "$frameworkRoot" ]] || return 0
	local item description
	# Sign Mach-O contents first, then enclosing framework bundles from inside out.
	while IFS= read -r -d '' item; do
		description=$(/usr/bin/file -b "$item") || panic 1 "Cannot inspect embedded code: $item"
		if [[ "$description" == *Mach-O* ]]; then
			/usr/bin/codesign --force --sign "$EXPANDED_CODE_SIGN_IDENTITY" --timestamp=none --generate-entitlement-der "$item" || panic 1 "Failed to sign embedded code: $item"
		fi
	done < <(/usr/bin/find "$frameworkRoot" -type f -print0)
	while IFS= read -r -d '' item; do
		/usr/bin/codesign --force --sign "$EXPANDED_CODE_SIGN_IDENTITY" --timestamp=none --generate-entitlement-der "$item" || panic 1 "Failed to sign framework: $item"
	done < <(/usr/bin/find "$frameworkRoot" -depth -type d -name '*.framework' -print0)
}

if [[ "$1" == "codesign" ]]; then
	if [[ ${MONKEYDEV_INSERT_DYLIB} == "NO" ]];then
		rm -rf "${BUILD_APP_PATH}/Frameworks/lib${TARGET_NAME}Dylib.dylib"
	fi
	# Reapply after Xcode's ProcessInfoPlistFile; never edit the project/input plist.
	source "${MONKEYDEV_PATH}/Tools/reveal.sh" || panic 1 "Cannot load Reveal integration"
	configureRevealDiscovery
	removeDeviceRestriction "${BUILD_APP_PATH}/Info.plist"
	signEmbeddedCode
	signMainApp
else
	pack
fi
