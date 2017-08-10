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
unsign="$MONKEYDEV_PATH/bin/unsign"
optool="$MONKEYDEV_PATH/bin/optool"
restoresymbol="$MONKEYDEV_PATH/bin/restore-symbol"

#exename
TARGET_APP_PATH=$(find "$SRCROOT/$TARGET_NAME/TargetApp" -type d | grep ".app$" | head -n 1)

if [[ "$TARGET_APP_PATH" == "" ]]; then
	panic 1 "cannot find target app"
fi

APP_BINARY_NAME=`plutil -convert xml1 -o - $TARGET_APP_PATH/Contents/Info.plist | grep -A1 Exec | tail -n1 | cut -f2 -d\> | cut -f1 -d\<`
APP_BINARY_PATH="$TARGET_APP_PATH/Contents/MacOS/$APP_BINARY_NAME"

#restoresymbol
if [[ ! -f "$APP_BINARY_PATH".symbol ]]; then
	"$restoresymbol" "$APP_BINARY_PATH" -o "$APP_BINARY_PATH"_with_symbol
	mv "$APP_BINARY_PATH"_with_symbol "$APP_BINARY_PATH"
	echo "restoresymbol" >> "$APP_BINARY_PATH".symbol
fi

#unsign
if [[ ! -f "$APP_BINARY_PATH".unsigned ]]; then
	"$unsign" "$APP_BINARY_PATH"
	mv "$APP_BINARY_PATH".unsigned "$APP_BINARY_PATH"
	echo "unsigned" >> "$APP_BINARY_PATH".unsigned
fi

#insert dylib
BUILD_DYLIB_PATH="$BUILT_PRODUCTS_DIR/lib$TARGET_NAME.dylib"

if [[ ! -f "$APP_BINARY_PATH".insert ]]; then
	"$optool" install -c load -p "@executable_path/lib$TARGET_NAME.dylib" -t "$APP_BINARY_PATH"
	echo "insert" >> "$APP_BINARY_PATH".insert
fi

cp -rf "$BUILD_DYLIB_PATH" "$TARGET_APP_PATH/Contents/MacOS/"

chmod +x "$APP_BINARY_PATH"

"$APP_BINARY_PATH"
