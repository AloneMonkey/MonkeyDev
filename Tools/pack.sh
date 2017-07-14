echo "packing..."
# environment
TEMP_PATH="${SRCROOT}/$TARGET_NAME/tmp"
MONKEYDEV_TOOLS="/opt/MonkeyDev/Tools/"
DEMOTARGET_APP_PATH="/opt/MonkeyDev/Resource/TargetApp.app"
OPTOOL="$MONKEYDEV_TOOLS/optool"
FRAMEWORKS_TO_INJECT_PATH="/opt/MonkeyDev/Frameworks/"
CUSTOM_DISPLAY_NAME=$(/usr/libexec/PlistBuddy -c "Print CFBundleDisplayName"  "${SRCROOT}/$TARGET_NAME/Info.plist")
CUSTOM_BUNDLE_ID="$PRODUCT_BUNDLE_IDENTIFIER"

rm -rf "$TEMP_PATH" || true
mkdir -p "$TEMP_PATH" || true

#deal ipa or app
TARGET_IPA_PATH=$(find "$SRCROOT/$TARGET_NAME/TargetApp" -type f | grep ".ipa$" | head -n 1)

echo "target ipa:$TARGET_IPA_PATH"

if [[ "$TARGET_IPA_PATH" != "" ]]; then
	unzip -oqq "$TARGET_IPA_PATH" -d "$TEMP_PATH"
	TEMP_APP_PATH=$(set -- "$TEMP_PATH/Payload/"*.app; echo "$1")
	cp -rf "$TEMP_APP_PATH" "$SRCROOT/$TARGET_NAME/TargetApp/"
fi

BUILD_APP_PATH="$BUILT_PRODUCTS_DIR/$TARGET_NAME.app"
TARGET_APP_PATH=$(find "$SRCROOT/$TARGET_NAME/TargetApp" -type d | grep ".app$" | head -n 1)

echo "target app:$TARGET_APP_PATH"
if [[ "$TARGET_APP_PATH" != "" ]]; then
	cp -rf "$TARGET_APP_PATH/" "$BUILD_APP_PATH/"
	echo "copy $TARGET_APP_PATH to $BUILD_APP_PATH"
else
	cp -rf "$DEMOTARGET_APP_PATH/" "$BUILD_APP_PATH/"
fi

# copy default framewrok
TARGET_APP_FRAMEWORKS_PATH="$BUILD_APP_PATH/Frameworks/"

if [ ! -d "$TARGET_APP_FRAMEWORKS_PATH" ]; then
	mkdir -p "$TARGET_APP_FRAMEWORKS_PATH"
fi

cp -rf "$BUILT_PRODUCTS_DIR/lib""$TARGET_NAME""Dylib.dylib" "$TARGET_APP_FRAMEWORKS_PATH"
cp -rf "$FRAMEWORKS_TO_INJECT_PATH" "$TARGET_APP_FRAMEWORKS_PATH"

# Inject the Dynamic Lib
APP_BINARY=`plutil -convert xml1 -o - $BUILD_APP_PATH/Info.plist|grep -A1 Exec|tail -n1|cut -f2 -d\>|cut -f1 -d\<`

"$OPTOOL" install -c load -p "@executable_path/Frameworks/lib""$TARGET_NAME""Dylib.dylib" -t "$BUILD_APP_PATH/$APP_BINARY"

chmod +x "$BUILD_APP_PATH/$APP_BINARY"

# remove Plugin an Watch
rm -rf "$BUILD_APP_PATH/PlugIns" || true
rm -rf "$BUILD_APP_PATH/Watch" || true

# Update Info.plist for Target App
if [[ "$CUSTOM_DISPLAY_NAME" != "" ]]; then
	/usr/libexec/PlistBuddy -c "Set :CFBundleDisplayName $CUSTOM_DISPLAY_NAME" "$BUILD_APP_PATH/Info.plist"
fi
/usr/libexec/PlistBuddy -c "Set :CFBundleIdentifier $PRODUCT_BUNDLE_IDENTIFIER" "$BUILD_APP_PATH/Info.plist"

#codesign
if [ -d "$TARGET_APP_FRAMEWORKS_PATH" ]; then
for FRAMEWORK in "$TARGET_APP_FRAMEWORKS_PATH/"*
do
    FILENAME=$(basename $FRAMEWORK)
    /usr/bin/codesign --force --sign "$EXPANDED_CODE_SIGN_IDENTITY" "$FRAMEWORK"
done
fi

MOBILEPROVISION_PATH=$(find "$BUILD_APP_PATH/" -type f | grep ".mobileprovision$" | head -n 1)

if [ -f "$MOBILEPROVISION_PATH" ]; then
	/usr/bin/security cms -D -i "$MOBILEPROVISION_PATH" > "$TEMP_PATH/"profile.plist
	/usr/libexec/PlistBuddy -x -c 'Print :Entitlements' "$TEMP_PATH/"profile.plist > "$TEMP_PATH/"entitlements.plist
	/usr/bin/codesign --force --sign "$EXPANDED_CODE_SIGN_IDENTITY" --entitlements "$TEMP_PATH/"entitlements.plist "$BUILD_APP_PATH"
fi



