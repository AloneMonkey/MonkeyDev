MONKEYDEV_PATH="/opt/MonkeyDev"

function panic() # args: exitCode, message...
{
	local exitCode=$1
	set +e
	
	shift
	[[ "$@" == "" ]] || \
		echo "$@" >&2

	exit $exitCode
}

echo "packing..."
# environment
monkeyparser="$MONKEYDEV_PATH/bin/monkeyparser"
substrate="$MONKEYDEV_PATH/MFrameworks/libsubstitute.dylib"

#exename
TARGET_APP_PATH=$(find "$SRCROOT/$TARGET_NAME/TargetApp" -type d | grep ".app$" | head -n 1)

if [[ "$TARGET_APP_PATH" == "" ]]; then
	panic 1 "cannot find target app"
fi

APP_BINARY_NAME=`plutil -convert xml1 -o - "$TARGET_APP_PATH/Contents/Info.plist" | grep -A1 CFBundleExecutable | tail -n1 | cut -f2 -d\> | cut -f1 -d\<`
APP_BINARY_PATH="$TARGET_APP_PATH/Contents/MacOS/$APP_BINARY_NAME"

#restoresymbol
if [[ ! -f "$APP_BINARY_PATH".symbol ]]; then
	"$monkeyparser" restoresymbol -t "$APP_BINARY_PATH" -o "$APP_BINARY_PATH"_with_symbol
	mv "$APP_BINARY_PATH"_with_symbol "$APP_BINARY_PATH"
	echo "restoresymbol" >> "$APP_BINARY_PATH".symbol
fi

#unsign
if [[ ! -f "$APP_BINARY_PATH".unsigned ]]; then
	"$monkeyparser" strip -t "$APP_BINARY_PATH" -o "$APP_BINARY_PATH".unsigned
	mv "$APP_BINARY_PATH".unsigned "$APP_BINARY_PATH"
	echo "unsigned" >> "$APP_BINARY_PATH".unsigned
fi

#insert dylib
BUILD_DYLIB_PATH="$BUILT_PRODUCTS_DIR/lib$TARGET_NAME.dylib"

if [[ ! -f "$APP_BINARY_PATH".insert ]]; then
	cp -rf "$substrate" "$TARGET_APP_PATH/Contents/MacOS/"
	"$monkeyparser" install -c load -p "@executable_path/lib$TARGET_NAME.dylib" -t "$APP_BINARY_PATH"
	echo "insert" >> "$APP_BINARY_PATH".insert
fi

cp -rf "$BUILD_DYLIB_PATH" "$TARGET_APP_PATH/Contents/MacOS/"

chmod +x "$APP_BINARY_PATH"

"$APP_BINARY_PATH"
