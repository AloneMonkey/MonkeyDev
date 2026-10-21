# LookinServer 1.2.8

Bundled iOS arm64 dynamic framework, built with Xcode 27 / iPhoneOS 27 SDK, deployment target iOS 15.0. Used only when MonkeyApp selects Lookin in Debug. The macOS Lookin client is installed separately.

- Upstream: https://github.com/QMUI/LookinServer/tree/e553d1b689d147817dc54ad5c28fcff71e860101 (tag 1.2.8).
- Original source archive: `LookinServer-1.2.8-source.tar.gz`, SHA-256 `2884d1d490c6d965246d27197f4ccf7f2776f5ae252bb092bb61c6e1c639f733`.
- License: upstream MIT text in `LookinServer.framework/LICENSE`; copyright notices and the complete original source are preserved.
- No Swift subspec is included. The framework is copied into the build product and signed with the App; the bundled SDK remains unchanged.
- Override with `MONKEYDEV_LOOKIN_SDK` when another iOS arm64 dynamic framework is needed.

## Build inputs

Extract the included archive and compile all `.m`, `.mm`, and `.c` files under `Src/Main` and `Src/Base`, with every directory under `Src` on the header search path. The build uses:

```text
xcrun clang -target arm64-apple-ios15.0 -isysroot <iphoneos-sdk>
  -dynamiclib -fobjc-arc -fmodules -fmodules-cache-path=<temporary-cache>
  -DSHOULD_COMPILE_LOOKIN_SERVER=1 -DDEBUG=1 -Wno-deprecated-declarations
  -framework UIKit -framework Foundation -framework QuartzCore -framework CoreGraphics
  -Wl,-install_name,@rpath/LookinServer.framework/LookinServer
  <header-search-paths> <sources> -o LookinServer.framework/LookinServer
```

The accompanying Info.plist declares the framework executable, iPhoneOS platform, minimum iOS 15.0 and version 1.2.8. Project builds do not download or compile this source archive.
