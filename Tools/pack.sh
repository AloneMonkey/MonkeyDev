MONKEYDEV_PATH="/opt/MonkeyDev"
TEMP_PATH="${SRCROOT}/$TARGET_NAME/tmp"
MONKEYPARSER="$MONKEYDEV_PATH/bin/monkeyparser"
CREATE_IPA="$MONKEYDEV_PATH/bin/createIPA.command"
CLASS_DUMP_TOOL="$MONKEYDEV_PATH/bin/class-dump"

function panic() # args: exitCode, message...
{
	local exitCode=$1
	set +e
	
	shift
	[[ "$@" == "" ]] || \
		echo "$@" >&2

	exit $exitCode
}

function codesign()
{
    for file in `ls "$1"`;
    do
		extension="${file#*.}"
        if [[ -d "$1/$file" ]]; then
			if [[ "$extension" == "framework" ]]; then
        			/usr/bin/codesign --force --sign "$EXPANDED_CODE_SIGN_IDENTITY" "$1/$file"
			else
				codesign "$1/$file"
			fi
		elif [[ -f "$1/$file" ]]; then
			if [[ "$extension" == "dylib" ]]; then
        			/usr/bin/codesign --force --sign "$EXPANDED_CODE_SIGN_IDENTITY" "$1/$file"
        	fi
        fi
    done
}

function checkApp(){
	TARGET_APP_PATH="$1"

	# remove Plugin an Watch
	rm -rf "$TARGET_APP_PATH/PlugIns" || true
	rm -rf "$TARGET_APP_PATH/Watch" || true

	VERIFY_RESULT=`"$MONKEYPARSER" verify -t "$TARGET_APP_PATH"`

	if [[ "$VERIFY_RESULT" != "" ]]; then
		panic 1 "$VERIFY_RESULT"
	fi

	MACH_O_FILE_NAME=`plutil -convert xml1 -o - "$TARGET_APP_PATH/Info.plist" | grep -A1 Exec | tail -n1 | cut -f2 -d\> | cut -f1 -d\<`
	MACH_O_FILE_PATH="$TARGET_APP_PATH/$MACH_O_FILE_NAME"
	ARMV7=false
 	ARM64=false
 	FAT_FILE=false
 	[[ $(lipo -info "$MACH_O_FILE_PATH" | grep armv7) == "" ]] || ARMV7=true
 	[[ $(lipo -info "$MACH_O_FILE_PATH" | grep arm64) == "" ]] || ARM64=true
 	[[ $(lipo -info "$MACH_O_FILE_PATH" | grep "Non-fat file") != "" ]] || FAT_FILE=true
 	echo "has arm7 arch? $ARMV7"
 	echo "has arm64 arch? $ARM64"
 	echo "is fat file? $FAT_FILE"
 	if [[ ! ARMV7 && ! ARM64 ]]; then
  		panic 1 "The target does not contain armv7 or arm64 arch!!!"
 	fi
 	decrypted_num=$(otool -l "$MACH_O_FILE_PATH" | grep "cryptid 0" | wc -l | tr -d " ")
 	echo "decrypted arch num? $decrypted_num"
 	if [[ "$decrypted_num" == "0" ]]; then
 		panic 1 "can't find decrypted arch!!!"
 	fi
 	if [[ "$decrypted_num" == "1" ]] && "$FAT_FILE"; then
 		if "$ARMV7"; then
 			lipo -thin armv7 $MACH_O_FILE_PATH -o $MACH_O_FILE_PATH
 		fi
 		if "$ARM64"; then
 			lipo -thin arm64 $MACH_O_FILE_PATH -o $MACH_O_FILE_PATH
 		fi
 	fi
 	#class_dump
 	if [[ ! -f "$TARGET_APP_PATH"/md_class_dump ]] && [[ "${MONKEYDEV_CLASS_DUMP}" == "YES" ]]; then
 		TARGET_DUMP_DIR="${SRCROOT}/$TARGET_NAME/$MACH_O_FILE_NAME"_Headers
 		if [[ -d "$TARGET_DUMP_DIR" ]]; then
 			rm -rf "$TARGET_DUMP_DIR" || true
 		fi
 		mkdir -p "$TARGET_DUMP_DIR"

 		if "$FAT_FILE" && "$ARMV7" && "$ARM64" && [[ "$decrypted_num" == "1" ]]; then
 			decrypted_arch="arm64"
 			lipo -thin armv7 $MACH_O_FILE_PATH -o $TEMP_PATH/"$MACH_O_FILE_NAME"_armv7
			lipo -thin arm64 $MACH_O_FILE_PATH -o $TEMP_PATH/"$MACH_O_FILE_NAME"_arm64
 			[[ $(otool -l $TEMP_PATH/"$MACH_O_FILE_NAME"_armv7 | grep "cryptid 0") == "" ]] || decrypted_arch="armv7"
 			[[ $(otool -l $TEMP_PATH/"$MACH_O_FILE_NAME"_arm64 | grep "cryptid 0") == "" ]] || decrypted_arch="arm64"
 			echo "current decrypted arch: $decrypted_arch"
 			"$CLASS_DUMP_TOOL" "$MACH_O_FILE_PATH" --arch "$decrypted_arch" -H -o "$TARGET_DUMP_DIR"
 		else
 			"$CLASS_DUMP_TOOL" "$MACH_O_FILE_PATH" -H -o "$TARGET_DUMP_DIR"
 		fi
 		echo "finsih_class_dump" >> "$TARGET_APP_PATH"/md_class_dump
 	fi

 	#restore_symbol
 	if [[ ! -f "$TARGET_APP_PATH"/md_restore_symbol ]] && [[ "${MONKEYDEV_RESTORE_SYMBOL}" == "YES" ]]; then
 		if "$FAT_FILE"; then
 			if "$ARMV7" && "$ARM64"; then
 				echo "fat: armv7 and arm64"
 				lipo -thin armv7 "$MACH_O_FILE_PATH" -o "$TEMP_PATH/$MACH_O_FILE_NAME"_armv7
				lipo -thin arm64 "$MACH_O_FILE_PATH" -o "$TEMP_PATH/$MACH_O_FILE_NAME"_arm64
				"$MONKEYPARSER" restoresymbol -t "$TEMP_PATH/$MACH_O_FILE_NAME"_armv7 -o "$TEMP_PATH/$MACH_O_FILE_NAME"_armv7_with_symbol
				"$MONKEYPARSER" restoresymbol -t "$TEMP_PATH/$MACH_O_FILE_NAME"_arm64 -o "$TEMP_PATH/$MACH_O_FILE_NAME"_arm64_with_symbol
				lipo -create "$TEMP_PATH/$MACH_O_FILE_NAME"_armv7_with_symbol "$TEMP_PATH/$MACH_O_FILE_NAME"_arm64_with_symbol -o "$TEMP_PATH/$MACH_O_FILE_NAME"_with_symbol
				cp -rf "$TEMP_PATH/$MACH_O_FILE_NAME"_with_symbol "$MACH_O_FILE_PATH"
			elif "$ARMV7"; then
				echo "fat: armv7"
				lipo -thin armv7 "$MACH_O_FILE_PATH" -o "$TEMP_PATH/$MACH_O_FILE_NAME"_armv7
				"$MONKEYPARSER" restoresymbol -t "$TEMP_PATH/$MACH_O_FILE_NAME"_armv7 -o "$TEMP_PATH/$MACH_O_FILE_NAME"_armv7_with_symbol
	 			cp -rf "$TEMP_PATH/$MACH_O_FILE_NAME"_armv7_with_symbol "$MACH_O_FILE_PATH"
 			elif "$ARM64"; then
 				echo "fat: arm64"
 				lipo -thin arm64 "$MACH_O_FILE_PATH" -o "$TEMP_PATH/$MACH_O_FILE_NAME"_arm64
 				"$MONKEYPARSER" restoresymbol -t "$TEMP_PATH/$MACH_O_FILE_NAME"_arm64 -o "$TEMP_PATH/$MACH_O_FILE_NAME"_arm64_with_symbol
	 			cp -rf "$TEMP_PATH/$MACH_O_FILE_NAME"_arm64_with_symbol "$MACH_O_FILE_PATH"
 			fi
	 	elif "$ARMV7"; then
	 		echo "armv7"
	 		"$MONKEYPARSER" restoresymbol -t "$MACH_O_FILE_PATH" -o "$TEMP_PATH/$MACH_O_FILE_NAME"_armv7_with_symbol
	 		cp -rf $TEMP_PATH/"$MACH_O_FILE_NAME"_armv7_with_symbol "$MACH_O_FILE_PATH"
	 	elif "$ARM64"; then
	 		echo "arm64"
	 		"$MONKEYPARSER" restoresymbol -t "$MACH_O_FILE_PATH" -o "$TEMP_PATH/$MACH_O_FILE_NAME"_arm64_with_symbol
	 		cp -rf $TEMP_PATH/"$MACH_O_FILE_NAME"_arm64_with_symbol "$MACH_O_FILE_PATH"
	 	fi
	 	echo "finsih_restore_symbol" >> "$TARGET_APP_PATH"/md_restore_symbol
 	fi
}

BUILD_APP_PATH="$BUILT_PRODUCTS_DIR/$TARGET_NAME.app"

function pack(){
	echo "packing..."

	# environment
	MONKEYDEV_TOOLS="$MONKEYDEV_PATH/Tools/"
	DEMOTARGET_APP_PATH="$MONKEYDEV_PATH/Resource/TargetApp.app"
	FRAMEWORKS_TO_INJECT_PATH="$MONKEYDEV_PATH/Frameworks/"
	CUSTOM_DISPLAY_NAME=$(/usr/libexec/PlistBuddy -c "Print CFBundleDisplayName"  "${SRCROOT}/$TARGET_NAME/Info.plist")
	CUSTOM_URL_TYPE=$(/usr/libexec/PlistBuddy -x -c "Print CFBundleURLTypes"  "${SRCROOT}/$TARGET_NAME/Info.plist")
	CUSTOM_BUNDLE_ID="$PRODUCT_BUNDLE_IDENTIFIER"

	rm -rf "$TEMP_PATH" || true
	mkdir -p "$TEMP_PATH" || true

	rm -rf "${PROJECT_DIR}"/LatestBuild || true
	ln -fhs "${BUILT_PRODUCTS_DIR}" "${PROJECT_DIR}"/LatestBuild
	cp -rf "$CREATE_IPA" "${PROJECT_DIR}"/LatestBuild/

	#deal ipa or app
	TARGET_APP_PATH=$(find "$SRCROOT/$TARGET_NAME/TargetApp" -type d | grep ".app$" | head -n 1)
	TARGET_IPA_PATH=$(find "$SRCROOT/$TARGET_NAME/TargetApp" -type f | grep ".ipa$" | head -n 1)

	if [[ "$TARGET_APP_PATH" == "" ]] && [[ "$TARGET_IPA_PATH" != "" ]]; then
		unzip -oqq "$TARGET_IPA_PATH" -d "$TEMP_PATH"
		TEMP_APP_PATH=$(set -- "$TEMP_PATH/Payload/"*.app; echo "$1")
		cp -rf "$TEMP_APP_PATH" "$SRCROOT/$TARGET_NAME/TargetApp/"
	fi

	rm -rf "$BUILD_APP_PATH" || true
	mkdir -p "$BUILD_APP_PATH" || true

	TARGET_APP_PATH=$(find "$SRCROOT/$TARGET_NAME/TargetApp" -type d | grep ".app$" | head -n 1)
	if [[ "$TARGET_APP_PATH" != "" ]]; then
		checkApp "$TARGET_APP_PATH" 
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
	APP_BINARY=`plutil -convert xml1 -o - $BUILD_APP_PATH/Info.plist | grep -A1 Exec | tail -n1 | cut -f2 -d\> | cut -f1 -d\<`

	"$MONKEYPARSER" install -c load -p "@executable_path/Frameworks/lib""$TARGET_NAME""Dylib.dylib" -t "$BUILD_APP_PATH/$APP_BINARY"
	"$MONKEYPARSER" unrestrict -t "$BUILD_APP_PATH/$APP_BINARY"

	chmod +x "$BUILD_APP_PATH/$APP_BINARY"

	# Update Info.plist for Target App
	if [[ "$CUSTOM_DISPLAY_NAME" != "" ]]; then
		/usr/libexec/PlistBuddy -c "Set :CFBundleDisplayName $CUSTOM_DISPLAY_NAME" "$BUILD_APP_PATH/Info.plist"
		/usr/libexec/PlistBuddy -c "Set :CFBundleName $CUSTOM_DISPLAY_NAME" "$BUILD_APP_PATH/Info.plist"
		for file in `ls "$BUILD_APP_PATH"`;
		do
			extension="${file#*.}"
		    if [[ -d "$BUILD_APP_PATH/$file" ]]; then
				if [[ "$extension" == "lproj" ]]; then
					if [[ -f "$BUILD_APP_PATH/$file/InfoPlist.strings" ]];then
						/usr/libexec/PlistBuddy -c "Set :CFBundleDisplayName $CUSTOM_DISPLAY_NAME" "$BUILD_APP_PATH/$file/InfoPlist.strings"
						/usr/libexec/PlistBuddy -c "Set :CFBundleName $CUSTOM_DISPLAY_NAME" "$BUILD_APP_PATH/$file/InfoPlist.strings"
					fi
		    	fi
			fi
		done
	fi
	
	if [[ "$PRODUCT_BUNDLE_IDENTIFIER" != "aaa" ]]; then
		/usr/libexec/PlistBuddy -c "Set :CFBundleIdentifier $PRODUCT_BUNDLE_IDENTIFIER" "$BUILD_APP_PATH/Info.plist"
	fi
	
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

	#cocoapods
	if [[ -f "${SRCROOT}/Pods/Target Support Files/Pods-""$TARGET_NAME""Dylib/Pods-""$TARGET_NAME""Dylib-frameworks.sh" ]]; then
		source "${SRCROOT}/Pods/Target Support Files/Pods-""$TARGET_NAME""Dylib/Pods-""$TARGET_NAME""Dylib-frameworks.sh"
	fi

	if [[ -f "${SRCROOT}/Pods/Target Support Files/Pods-""$TARGET_NAME""Dylib/Pods-""$TARGET_NAME""Dylib-resources.sh" ]]; then
		source "${SRCROOT}/Pods/Target Support Files/Pods-""$TARGET_NAME""Dylib/Pods-""$TARGET_NAME""Dylib-resources.sh"
	fi

	if [[ -f "${SRCROOT}/../Pods/Target Support Files/Pods-""$TARGET_NAME""Dylib/Pods-""$TARGET_NAME""Dylib-frameworks.sh" ]]; then
		source "${SRCROOT}/../Pods/Target Support Files/Pods-""$TARGET_NAME""Dylib/Pods-""$TARGET_NAME""Dylib-frameworks.sh"
	fi

	if [[ -f "${SRCROOT}/../Pods/Target Support Files/Pods-""$TARGET_NAME""Dylib/Pods-""$TARGET_NAME""Dylib-resources.sh" ]]; then
		source "${SRCROOT}/../Pods/Target Support Files/Pods-""$TARGET_NAME""Dylib/Pods-""$TARGET_NAME""Dylib-resources.sh"
	fi

	mv "$BUILD_APP_PATH/Info.plist" "$BUILD_APP_PATH/Info.plist.bak" 
}

if [[ "$1" == "codesign" ]]; then
	mv "$BUILD_APP_PATH/Info.plist.bak" "$BUILD_APP_PATH/Info.plist" 
	codesign "$BUILD_APP_PATH"
else
	pack
fi