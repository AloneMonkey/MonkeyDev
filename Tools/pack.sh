function codesign()
{
    for file in `ls $1`;
    do
		extension="${file#*.}"
        if [[ -d "$1/$file" ]]; then
        	if [[  "$extension" == "framework" ]]; then
        		/usr/bin/codesign --force --sign "$EXPANDED_CODE_SIGN_IDENTITY" "$1/$file"
        	fi
            codesign "$1/$file"
        fi
    done
}

echo "packing..."
# environment
MONKEYDEV_PATH="/opt/MonkeyDev"
TEMP_PATH="${SRCROOT}/$TARGET_NAME/tmp"
MONKEYDEV_TOOLS="$MONKEYDEV_PATH/Tools/"
DEMOTARGET_APP_PATH="$MONKEYDEV_PATH/Resource/TargetApp.app"
OPTOOL="$MONKEYDEV_PATH/bin/optool"
FRAMEWORKS_TO_INJECT_PATH="$MONKEYDEV_PATH/Frameworks/"
CUSTOM_DISPLAY_NAME=$(/usr/libexec/PlistBuddy -c "Print CFBundleDisplayName"  "${SRCROOT}/$TARGET_NAME/Info.plist")
CUSTOM_URL_TYPE=$(/usr/libexec/PlistBuddy -x -c "Print CFBundleURLTypes"  "${SRCROOT}/$TARGET_NAME/Info.plist")
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

rm -rf "$BUILD_APP_PATH" || true
mkdir -p "$BUILD_APP_PATH" || true

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

if [[ -d "$SRCROOT/$TARGET_NAME/Resources" ]]; then
 for file in "$SRCROOT/$TARGET_NAME/Resources"/*; do
 	extension="${file#*.}"
  	filename="${file##*/}"
  	if [[ "$extension" == "storyboard" ]]; then
  		ibtool --compile "$BUILD_APP_PATH/$filename"c "$file"
  	else
  		cp -rf "$file" "$BUILD_APP_PATH/"
  	fi
 done
fi

# Inject the Dynamic Lib
APP_BINARY=`plutil -convert xml1 -o - $BUILD_APP_PATH/Info.plist|grep -A1 Exec|tail -n1|cut -f2 -d\>|cut -f1 -d\<`

"$OPTOOL" install -c load -p "@executable_path/Frameworks/lib""$TARGET_NAME""Dylib.dylib" -t "$BUILD_APP_PATH/$APP_BINARY"
"$OPTOOL" unrestrict -w -t "$BUILD_APP_PATH/$APP_BINARY"

chmod +x "$BUILD_APP_PATH/$APP_BINARY"

# remove Plugin an Watch
rm -rf "$BUILD_APP_PATH/PlugIns" || true
rm -rf "$BUILD_APP_PATH/Watch" || true

# Update Info.plist for Target App
if [[ "$CUSTOM_DISPLAY_NAME" != "" ]]; then
	/usr/libexec/PlistBuddy -c "Set :CFBundleDisplayName $CUSTOM_DISPLAY_NAME" "$BUILD_APP_PATH/Info.plist"
fi
/usr/libexec/PlistBuddy -c "Set :CFBundleIdentifier $PRODUCT_BUNDLE_IDENTIFIER" "$BUILD_APP_PATH/Info.plist"

#support URL Scheme
if [[ "$CUSTOM_URL_TYPE" != "" ]]; then
	CUSTOM_URL_TYPE_FILE="$TEMP_PATH"/url_type.plist
	CUSTOM_URL_TYPE_FILE_EX=$(echo "$CUSTOM_URL_TYPE_FILE" | sed "s/ /\\\ /g")
	echo "$CUSTOM_URL_TYPE" >> "$CUSTOM_URL_TYPE_FILE"
	ORIGIN_URL_TYPE=$(/usr/libexec/PlistBuddy -c "Print CFBundleURLTypes"  "$BUILD_APP_PATH/Info.plist")
	if [[ "$ORIGIN_URL_TYPE" == "" ]]; then
		/usr/libexec/PlistBuddy -x -c 'add CFBundleURLTypes array' "$BUILD_APP_PATH/Info.plist"
	fi
	/usr/libexec/PlistBuddy -x -c "merge $CUSTOM_URL_TYPE_FILE_EX CFBundleURLTypes" "$BUILD_APP_PATH/Info.plist"
fi

#codesign
# if [ -d "$TARGET_APP_FRAMEWORKS_PATH" ]; then
# for FRAMEWORK in "$TARGET_APP_FRAMEWORKS_PATH/"*
# do
#     /usr/bin/codesign --force --sign "$EXPANDED_CODE_SIGN_IDENTITY" "$FRAMEWORK"
# done
# fi

codesign "$BUILD_APP_PATH"

#cocoapods
if [[ -f "${SRCROOT}/Pods/Target Support Files/Pods-""$TARGET_NAME""Dylib/Pods-""$TARGET_NAME""Dylib-frameworks.sh" ]]; then
	source "${SRCROOT}/Pods/Target Support Files/Pods-""$TARGET_NAME""Dylib/Pods-""$TARGET_NAME""Dylib-frameworks.sh"
fi

if [[ -f "${SRCROOT}/Pods/Target Support Files/Pods-""$TARGET_NAME""Dylib/Pods-""$TARGET_NAME""Dylib-resources.sh" ]]; then
	source "${SRCROOT}/Pods/Target Support Files/Pods-""$TARGET_NAME""Dylib/Pods-""$TARGET_NAME""Dylib-resources.sh"
fi 
