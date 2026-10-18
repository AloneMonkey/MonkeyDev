---
name: monkeydev
description: >-
  使用 MonkeyDev 在 Apple Silicon Mac 上创建 Xcode MonkeyApp、MonkeyPod 插件库、越狱 Logos/CaptainHook Tweak 和 iOS 命令行工具，完成插件开发、签名打包、USB/SSH 安装，以及 LLDB 调试、OC 头文件导出、符号还原、Reveal 检查和方法追踪。
---

# MonkeyDev

使用 Xcode 完成已有 iOS App 的插件开发、重签名、真机安装与调试。工作流为：安装 MonkeyDev → 创建 MonkeyApp → 放入目标 IPA/App → 编写 dylib → Xcode Build/Run。优先使用已有工程；用户要求新建时再创建工程。不要将此流程替换成独立重打包脚本。

先区分任务：非越狱重签名使用 MonkeyApp；越狱设备向已安装 App 注入插件使用 Logos Tweak 或 CaptainHook Tweak；在设备 SSH 中运行程序使用 Command-line Tool。后两种流程见第 9 节，不需要把 App 放进 TargetApp，也不使用开发团队的 provisioning profile 安装 deb。

仓库：<https://github.com/AloneMonkey/MonkeyDev>。本文件可单独作为操作入口，无需先读取完整仓库文档。从分支或特定提交读取本文件时，使用同一版本的安装脚本和源码，避免新说明搭配旧模板。

## 1. 检查前提

- Apple Silicon Mac，使用原生 arm64 终端；完整 Xcode 已安装并完成首次启动配置。
- MonkeyApp：iPhone 开启开发者模式、信任此 Mac，并在安装启动时保持解锁。准备可用的开发团队、签名证书及授权该设备的 provisioning profile；Personal Team 的实际限制由 Xcode/Apple 决定。
- MonkeyApp 输入为已砸壳的 IPA 或未加密 `.app`，主程序及保留的嵌入代码应符合 thin arm64 范围。MonkeyDev 不负责在非越狱设备上自动砸壳。
- 当前支持基线为 iOS 15+、arm64 真机。MonkeyApp 不覆盖 Intel 主机、模拟器、Fat 输入、arm64e/PAC 或加密输入；设备 CPU 为 arm64e 不妨碍运行 arm64 App。越狱三个模板的 rootless arm64 已真机验证，rootful 仅完成构建与打包检查。

先检查：

```bash
uname -m
xcode-select -p
xcodebuild -version
xcrun --sdk iphoneos --show-sdk-path
```

`uname -m` 应为 `arm64`。若选中的是 CommandLineTools 而非完整 Xcode，选择实际的 Xcode Developer 目录；默认位置可用：

```bash
sudo xcode-select -s /Applications/Xcode.app/Contents/Developer
```

## 2. 安装与更新

### 安装 Theos

Logos 预处理使用普通用户的 `~/theos`。已有该目录时先确认 `~/theos/bin/logos.pl` 可执行，不覆盖用户现有安装。不使用 `/opt/theos`。

没有安装时，以普通用户执行，不加 sudo：

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/theos/theos/master/bin/install-theos)"
```

### 安装 MonkeyDev

使用已发布到 master、与本说明匹配的版本时：

```bash
sudo /bin/sh -c "$(curl -fsSL https://raw.githubusercontent.com/AloneMonkey/MonkeyDev/master/bin/md-install)"
/opt/MonkeyDev/bin/md-doctor
```

默认安装到 `/opt/MonkeyDev`，模板注册在当前用户的 `~/Library/Developer/Xcode/Templates/MonkeyDev`。完整模板来自 `MonkeyDev-Xcode-Templates` 仓库，安装器直接校验并安装，不再打补丁；需要测试本地模板修改时，通过 `MONKEYDEV_TEMPLATES_DIR` 显式指定其目录。安装器不修改 Xcode.app。正常安装已包含原生 monkeyparser 和 class-dump，无需额外编译 Capstone/Keystone 或安装 CMake。

安装器固定模板提交，不会因为更新本地 MonkeyDev 源码就自动使用本地模板。需要同时验证两仓库的未发布改动时，在下面安装或更新命令的 `env` 参数中另加 `MONKEYDEV_TEMPLATES_DIR="本地模板仓库的绝对路径"`。发布时先提交模板，再将安装器的默认模板 ref 更新为该提交；没有发布新模板前，不把远程 master 安装视为本地版本的验证。

**本地开发版或未发布改动：** 不执行上面的远程 master 安装命令代替本地安装。在包含这些改动的 MonkeyDev 源码根目录执行：

```bash
sudo env MONKEYDEV_SOURCE_DIR="$PWD" /bin/bash bin/md-install
/opt/MonkeyDev/bin/md-doctor
```

远程更新与本地源码更新分别使用：

```bash
# 更新已发布版本：
sudo /opt/MonkeyDev/bin/md-update

# 更新当前本地源码版本，在其源码根目录执行：
sudo env MONKEYDEV_SOURCE_DIR="$PWD" /bin/bash bin/md-update
```

安装后保存工作并重启 Xcode 刷新模板缓存。更新模板只影响新建工程，不会自动迁移已有工程。若版本中没有 `md-doctor` 或缺少下文选项，先确认是否装到了旧版，不据此修改 Xcode 私有文件。

管理员密码只在终端或 macOS 授权窗口输入，不在聊天中索取。若管理员进程被 macOS 隐私限制阻止读取 Documents 中的源码，可从可读取的临时发行副本运行相同安装器；安装锁或失败恢复目录存在时，先确认没有安装进程并检查恢复信息，不直接删除旧安装。

## 3. 创建与运行工程

1. Xcode → File → New → Project，选择 **MonkeyDev → MonkeyApp**。
2. 填写 Product Name、Team、Organization Identifier。使用用户实际的签名团队；不要照搬其他工程的 Team ID、Bundle ID 或设备 UDID。
3. `Target App` 保持 `Optional`。这个文本框是历史越狱 dump 入口，不是 IPA 文件路径选择器。
4. 创建工程后，将一个已砸壳 IPA 或未加密 `.app` 放到 `<App target 目录>/TargetApp/`。保持只有一份明确输入，避免脚本选到其他旧 App。没有输入时使用内置 Demo，可先验证基础环境。
5. App target → Signing & Capabilities，选择团队，确认项目 Bundle ID 可由该团队签名。
6. 选择连接的 iPhone，用 Debug 执行 Run。无需配置 `MONKEYDEV_INPUT_APP`，沿用 TargetApp 文件夹输入方式即可。

向导提供以下下拉项；创建后在 **App target → Build Settings → User-Defined** 修改，别改错到 Dylib target：

| 向导项 | Build Setting | 默认 | 用途 |
| --- | --- | --- | --- |
| Inject Dylib | `MONKEYDEV_INSERT_DYLIB` | YES | 注入本工程 dylib |
| Keep Original Bundle ID | `MONKEYDEV_DEFAULT_BUNDLEID` | NO | YES 时保留输入 App 的 Bundle ID |
| Restore OC Symbols | `MONKEYDEV_RESTORE_SYMBOL` | NO | 还原 OC 方法符号以便符号断点与调用栈分析 |
| Export OC Headers | `MONKEYDEV_CLASS_DUMP` | NO | 导出主程序 OC 头文件 |
| Reveal (Debug) | `MONKEYDEV_REVEAL` | NO | Debug 接入本机 Reveal SDK |

通常保持 Keep Original Bundle ID 为 NO，使用新工程的标识。YES 不会绕过签名授权；profile 必须允许原 ID，第三方原始 ID 常无法由当前团队注册。若用户明确要求保留，应说明实际签名限制，不自行换掉该 ID。

`MONKEYDEV_MINIMAL=YES` 保留默认值；不要为普通 Hook 打开旧 Substrate/Cycript 依赖。构建会在副本上移除 PlugIns、Watch 和旧 Store 元数据，当前不支持这些扩展的独立签名与安装。保留原始 IPA/App，不直接修改输入包。

## 4. 编写插件

工程通常包含两个同时编译的入口：

```text
<项目名>Dylib/
  <项目名>Dylib.m           普通 Objective-C / CaptainHook
  Logos/
    <项目名>Dylib.xm        Logos 源文件，修改这里
    <项目名>Dylib.mm        预处理生成文件，不手改
```

普通 `.m` 与 Logos 生成的 `.mm` 都能生效。先阅读现有 Hook 再修改，避免重复注册或两处同时展示相同弹窗。模板默认只打印示例日志。

### Logos 示例

在 `.xm` 中修改现有对应 Hook；下面是完整示例，不要重复追加同一段：

```objc
%config(generator=internal);
#import <UIKit/UIKit.h>

%hook UIViewController
- (void)viewDidAppear:(BOOL)animated {
    %orig(animated);
    static BOOL logged = NO;
    if (!logged) {
        logged = YES;
        NSLog(@"[MonkeyDev] Hook executed: %@", NSStringFromClass(self.class));
    }
}
%end

%ctor {
    NSLog(@"[MonkeyDev] dylib loaded");
    %init;
}
```

替换成目标 App 的实际类、selector 与准确方法签名，保留适当的原方法调用。构建时由 `~/theos/bin/logos.pl` 生成 `.mm`。internal 后端支持 OC 方法 Hook、`%orig`、`%ctor`，不支持 `%hookf`。

普通 `.m` 已提供 CaptainHook 示例，使用内部 Objective-C runtime 后端，不依赖 Substrate。保持 `CHUseSubstrate` 未定义，定义为 0 也可能命中 `#ifdef`。fishhook 用于导入符号重绑定，不是任意函数入口 Hook。

若任务是启动后弹窗，等待前台窗口和可展示的控制器就绪，再在主线程展示 `UIAlertController`，只展示一次；不要在 dylib constructor 中直接弹窗。测试代码放在当前用户工程，不把业务类或测试弹窗写进通用模板。

## 5. LLDB、符号和头文件

### 源码断点与符号断点

用 Debug 从 Xcode 启动。普通 `.m` 在实际语句上设断点；Logos 在 `.xm` 的实际语句上设断点，生成代码通过 `#line` 映射回源文件。若 `.xm` 无法点击行号设断点，核对其 Xcode File Type 为 Objective-C++，并保持它不作为额外编译源文件；实际编译的是生成 `.mm`。

要分析原 App 的 OC 方法，开启 `MONKEYDEV_RESTORE_SYMBOL=YES` 后重新构建。在 Xcode LLDB 控制台逐条执行：

```lldb
image lookup -n '-[YourClass yourMethod:]'
breakpoint set -n '-[YourClass yourMethod:]'
```

把示例换成真实完整符号，保留 selector 的全部冒号。也可在断点导航器按 ⌘8，点击 ＋ → Symbolic Breakpoint，将方法符号填入 Symbol。

先确认符号能查到、断点有解析位置，再操作 App 触发相应路径。已解析却未命中可能只是调用了另一个重载或实现，不能直接判断符号还原失败。MonkeyApp 中，monkeyparser 负责 dylib 加载命令注入与独立的 OC 方法符号还原，系统 codesign 负责最终签名；越狱 deb 使用 ldid 签名，由设备 tweak 加载器加载，不经 monkeyparser 注入。

### Debug 查询辅助函数

优先使用带 `md_` 前缀的入口，避免与系统符号重名。UI 查询前选中主线程，在 LLDB 逐条执行：

```lldb
expr -l objc++ -O -- (id)md_pvc()
expr -l objc++ -O -- (id)md_pviews()
expr -l objc++ -O -- (id)md_methods("YourClass")
```

`md_pvc` 列控制器树，`md_pviews` 列视图树，`md_methods` 列 OC runtime 方法。`md_ivars((uintptr_t)地址)` 查询成员元数据，`md_pactions((uintptr_t)地址)` 查询 UIControl 的 target/action；地址必须是当前进程有效的存活对象。UI 查询不会自动调度到主线程。辅助函数只在 Debug 可用，不提供旧版堆扫描功能。

### 导出头文件

开启 `MONKEYDEV_CLASS_DUMP=YES` 后构建，头文件位于：

```text
<工程目录>/Headers/<App target 名>/
```

使用构建日志打印的路径。导出由独立 class-dump 完成，不需要另外执行 monkeyparser 的隐式导出。生成目录加入工程 `.gitignore`，不要加入 App target。输出供分析参考，不保证能当作完整 SDK 编译，也不还原纯 Swift 源码；无法解析的元数据可能产生警告或被跳过。

## 6. Reveal

1. 用户在 Reveal 桌面应用中下载 Server SDK，默认位置为：

   ```text
   ~/Library/Application Support/Reveal/RevealServer/RevealServer.xcframework
   ```

2. 设置 App target 的 `MONKEYDEV_REVEAL=YES`，用 Debug 重新构建并运行。自定义 SDK 路径使用 `MONKEYDEV_REVEAL_SDK`，值是 `.xcframework` 的完整路径。
3. 允许 App 的本地网络访问，在 Reveal 选择该运行中的 App。USB 连接已验证；检查层级和 Refresh 时保持 App 运行，不能停在断点上。

框架从用户本机 SDK 复制到构建副本，MonkeyDev 不捆绑新版 SDK。只在名为 Debug 的 iPhoneOS 配置接入，Release 忽略开关；开启但缺少 SDK 时构建会失败。

若看不到 App，依次检查构建产物：`Frameworks/RevealServer.framework/RevealServer` 存在、主程序包含对应加载命令、最终 Info.plist 的 NSBonjourServices 包含 `_reveal._tcp`、本地网络权限已允许、签名和设备连接正常。若连接超时，先确认未暂停调试器，再重试 USB 连接。列表中出现 App 只说明发现成功，还需能读取完整层级并刷新。

## 7. 方法追踪 Trace

Debug 下在类已加载后、启动阶段或调试器暂停时注册指定方法。在 LLDB 逐条执行：

```lldb
expr -l objc++ -O -- (id)md_trace_start("YourClass", "yourMethod:", (BOOL)0)
expr -l objc++ -O -- (id)md_trace_status()
expr -l objc++ -- (void)md_trace_set_descriptions((BOOL)0)
expr -l objc++ -- (void)md_trace_stop()
```

将示例类和方法换为真实目标。第三个参数 0 为实例方法，1 为类方法。也可在源码导入 `Trace/MDMethodTrace.h`，于 `#if DEBUG` 内调用相同函数。正式模板不会自动注册方法。

注册前确认方法签名符合范围：

- 返回值：void、对象、BOOL/bool、signed char、32/64 位有符号或无符号整数、float、double。
- 参数：无显式参数；一个上述标量或对象；或者两个对象参数。
- 不使用结构体、union、任意指针、SEL、Class、其他混合/更多参数、可变参数及特殊 ARC 所有权方法；不追踪 init/new/copy/alloc 等所有权方法族或 runtime 生命周期管理方法。

日志包含 before、args、return、after/after-throw。按 `call` 与 `thread` 配对；`depth` 只表示同一线程中被追踪的同步嵌套，独立和异步调用通常为 0。耗时是原方法同步耗时，仍包含嵌套追踪及调试暂停的影响，不是完整网络请求耗时。

对象 description 会执行应用代码；有副作用或开销疑虑时用 `md_trace_set_descriptions(NO)` 关闭，YES 恢复。每个方法最多采样 100 次，最多注册 128 个方法、深度 32。stop 关闭日志但不卸载包装，再次 start 不重置预算；需要重新采样时重启进程。

## 8. 故障处理与验收

| 现象 | 优先检查与处理 |
| --- | --- |
| 模板或向导选项没更新 | 重启 Xcode，确认用户模板链接指向当前 `/opt/MonkeyDev/templates`；已有工程不会自动迁移 |
| Logos 找不到或不生成代码 | 检查当前用户 `~/theos/bin/logos.pl` 和 include 路径；编辑 `.xm`，不要只改 `.mm` |
| 原 Bundle ID 无法签名 | 查看当前团队/profile 是否授权该 ID；设备 UDID 授权与 App ID 授权是不同问题 |
| 手机无法启动或安装中断 | 检查解锁、信任、开发者模式、描述文件和 Xcode 的具体错误；不要反复安装或删除 App 数据 |
| 第二次安装失败或符号/库残留 | 先 Clean Build Folder，再连续两次构建运行；检查当前安装脚本版本及完整签名，而非只看编译成功 |
| 修改源码后运行行为没变 | 区分仓库、`/opt/MonkeyDev` 和工程中的源码；同步安装不等于自动更新已有 dylib 源文件 |

从没有 pack-files 清单的旧版本升级后，先执行一次 **Product → Clean Build Folder**。保留打包与最终签名两个脚本阶段每次执行；不要通过添加输出文件让 Xcode 跳过它们。不要手动更改 Xcode.app 的私有规格文件，也不要自行拼造签名 entitlements。

用户要求验证时，记录实际工程、构建配置和开关，完成构建、完整签名检查、安装、启动及用户要求的功能检查。修改打包或签名流程后，再不改源码连续运行一次以覆盖增量构建。只修改文档则不重复真机安装。已有测试记录不能代替本次执行结果；Build Succeeded、进程启动或 Reveal 列表可见，也不能单独证明所有功能通过。

只读取用户当前请求需要的内容，不把 IPA、导出头文件、测试工程、证书或 profile 放进 MonkeyDev 仓库。默认保留用户输入和 App 数据；提交、推送及设备操作不由读取本 skill 自动授权。

## 9. 越狱 Tweak 与命令行工具

### 创建与构建

使用 **MonkeyDev → Logos Tweak / CaptainHook Tweak / Command-line Tool** 正式模板，不另建测试模板分类。默认 arm64、rootless、USB 连接。手机需有可用的 SSH 服务；tweak 还需兼容 MobileSubstrate 接口的加载环境，例如 ElleKit。Sileo 是包管理器，不是 Hook 框架。

主机依赖：

```bash
brew install ldid libusbmuxd libimobiledevice
# 仅密码认证需要：
brew install sshpass
```

Logos Tweak 另需当前普通用户的 `~/theos/bin/logos.pl` 和 Theos 对应的头文件、链接库。CaptainHook 默认使用内部 Objective-C Runtime 后端，不定义 `CHUseSubstrate`，不添加 `-lsubstrate`；纯 C/C++ 命令行工具不依赖 Theos。

创建向导只配置认证方式：

| SSH Authentication | Build 行为 | 账号密码 |
| --- | --- | --- |
| `None` | 只生成 deb，不连接或安装 | 置灰 |
| `KEY`（默认） | SSH 免密登录并自动安装 | 置灰，继承已有 SSH 配置 |
| `PASSWORD` | 使用密码登录并自动安装 | 启用，默认账号 `mobile`，密码必填 |

密码输入为普通文本，会写入生成工程；`NotPersisted` 只是不记住到下一次创建，不能视为安全存储。不要将含密码的工程配置提交或分享，已有密码优先留在不提交的本地 xcconfig 或密码文件中。构建阶段不打印环境变量。

USB 默认通过 inetcat 直连设备 SSH 端口 22，不启动 iproxy，不需要本地 2222 转发。设备选择优先级：`MonkeyDevDeviceUDID` → Xcode 选择的有效设备标识 → `idevice_id -l` 检测到的唯一 USB 设备；多设备无法确定目标时停止并让用户选择。

免密模式默认匹配 `~/.ssh/config` 的 `monkeydev-usb` 别名，沿用其中的用户、IdentityFile 或 ssh-agent；不要照搬其他人的私钥路径或假设当前 Mac 用户名就是设备账号。首次连接先在终端核对主机身份，例如：

```bash
ssh -o "ProxyCommand=inetcat -u <UDID> 22" -o "HostKeyAlias=monkeydev-usb-<UDID>" mobile@usb-iphone
```

把 `<UDID>` 和账号替换为实际值，使用已有密钥配置或 `-i`。USB 安装使用同一 HostKeyAlias，不关闭主机密钥检查。SSH 免密与 sudo 免密独立；mobile 安装 deb 仍需已有 sudo 权限和所需密码，不为了通过测试擅自放宽 sudo 权限。

### 高级连接与布局

只有用户需要时才修改 target 的 Build Settings：

| 设置 | 用途 |
| --- | --- |
| `MonkeyDevConnectionType` | 默认 `USB`；`IP` 直连局域网，`SSH` 继承 SSH 别名配置 |
| `MonkeyDevDeviceIP` | 默认 `monkeydev-usb`；IP 模式填地址，SSH 模式填别名 |
| `MonkeyDevDevicePort` | 默认设备端口 22；SSH 模式留空才会继承别名端口 |
| `MonkeyDevDeviceUser` / `MonkeyDevDeviceKey` | 可显式指定设备账号、私钥；免密默认留空继承配置 |
| `MonkeyDevDeviceUDID` | 可选，指定 USB 目标设备 |
| `MonkeyDevDevicePasswordFile` | 本机一行密码文件，用于密码登录或免密登录后的 sudo；优先于 `MonkeyDevDevicePassword` |
| `MonkeyDevDevicePassword` | 设备密码，可在本地 xcconfig 配置；KEY 模式下只供 sudo，不切换 SSH 登录方式 |
| `MONKEYDEV_PACKAGE_SCHEME` | 默认 `rootless`；确认设备为 rootful 后改成 `rootful` |
| `MonkeyDevkillProcessOnInstall` | 可选目标进程名，默认留空；不默认重启 SpringBoard |

私钥和密码文件支持 `~/` 或相对工程目录的路径。向导的 `KEY/PASSWORD` 将 `MonkeyDevInstallOnAnyBuild` 联动为 YES，`None` 为 NO，且脚本会阻止 None 安装；手动把该安装设置改为 NO 可关闭 KEY/PASSWORD 的每次 Build 安装。保留 rootless/rootful 路径映射辅助字段，不要求用户手动修改它们。

打包在临时副本完成，deb 输出到 `<工程目录>/Packages/`。资源仍放在工程 `Package/Library/...` 或 `Package/usr/...`，不要手工再套 `var/jb`；rootless 自动添加 `/var/jb` 前缀，架构为 `iphoneos-arm64`，rootful 使用传统路径和 `iphoneos-arm` 包架构，两者二进制均为 arm64。

### 源码与验收

- Logos Tweak：编辑 `<项目名>.xm`，编译生成的 `.mm`。默认通过 Theos 的 MobileSubstrate 接口链接，设备端可由 ElleKit 实现，不把旧 Substrate 库打入 deb；与 MonkeyApp 的 Logos internal 后端区分。
- CaptainHook Tweak：编辑 `<项目名>.mm`，使用实际类和方法签名，在类已加载且存在时注册 Hook。模板只提供示例，不内置特定 App 的弹窗。
- 两种 tweak 均需设置 `Package/Library/MobileSubstrate/DynamicLibraries/<项目名>.plist` 的 Filter/ Bundles 为目标 App 的 Bundle ID；默认占位 ID 不会命中用户 App。它们默认不带 LLDBTools、Trace 或 Reveal，不能假定 MonkeyApp 的辅助入口可用。
- Command-line Tool：支持 C、C++、Foundation、Core Foundation；没有 Core Data/Core Services 类型。源码通常为 `main.c`、`main.cpp` 或 `main.m`。默认无额外 entitlements，需权限时按具体用途配置；不默认开启 `platform-application`。
- 命令行工具安装到 rootless 的 `/var/jb/usr/bin/<项目名>` 或 rootful 的 `/usr/bin/<项目名>`，通过设备 SSH 执行；不把 Xcode Run 当作设备安装启动入口。

验收时先用 None 验证编译与 deb 内容，再按用户选择的认证方式验证自动安装。tweak 重启目标 App 后检查实际 Hook 命中；要求弹窗时还需确认可见，不能用手工 dlopen 或调用弹窗函数代替。命令行工具需在设备执行并检查输出与退出码。SSH 不通先区分 USB 设备识别、主机身份、SSH 登录与 sudo 安装失败，不把所有错误归结为端口转发。

## 10. MonkeyPod 本地插件库

需要跨工程复用 CaptainHook 插件时使用 MonkeyPod，不把它当作独立 App 或 deb 模板。当前已验证 iOS 15+ arm64、本地动态 Pod、MonkeyApp 签名安装和真机 Hook；发布流程未验收。

1. 通过 Homebrew 安装 CocoaPods：`brew install cocoapods`，确认 `pod --version` 可执行，不使用 sudo 安装 Pod。
2. Xcode 选择 **MonkeyDev → MonkeyPod**，生成 Objective-C framework、公开头文件和同目录的 podspec。修改 `.m` 的实际类和实例方法；默认示例可在内置 Demo 上验证 `getMyName` 返回 `MonkeyDevPod`。保持 CaptainHook 内部后端，不定义 `CHUseSubstrate`。
3. 在 MonkeyApp 工程根目录创建 Podfile，将 Pod 接到 **Dylib target**，不是 App target。示例中替换实际名称和路径：

   ```ruby
   require '/opt/MonkeyDev/Tools/cocoapods-compat'
   platform :ios, '15.0'
   target 'YourAppDylib' do
     use_frameworks! :linkage => :dynamic
     pod 'YourPlugin', :path => '../YourPlugin/YourPlugin'
   end
   ```

4. `:path` 指向 podspec 所在目录。执行 `pod install` 后打开 `.xcworkspace`，选择 MonkeyApp 的 App scheme，通过正常 Build/Run 流程安装。动态 framework 的 constructor 随加载执行；不要随意改成静态 Pod，避免仅含 Hook 函数的对象文件被链接器丢弃。
5. 检查最终 App 的 `Frameworks/<Pod名>.framework`、Dylib 的链接依赖和完整签名，再检查真机实际 Hook。默认示例的 Demo 界面显示 `MonkeyDevPod`；不能只凭 pod install 或 framework 编译成功认定插件已生效。

`cocoapods-compat.rb` 只在当前 Podfile 进程中适配已验证的 Xcode 27 字段：脚本数组转为字符串，framework 复制目的地转成等效表示，生成的 Pods 工程使用受支持格式。保留宿主工程版本，不修改 Xcode.app 或安装的 gem。旧解析器遇到其他 `dstSubfolder` 复制目录时会在保存工程前报错停止；不要移除检查强行安装。其他未知字段仍需评估，不能据此承诺所有第三方工程兼容。只更新 MonkeyPod 模板无需改 MonkeyApp 打包脚本，其已有流程会复制并签名 Pod framework。

默认 podspec 的源文件路径相对 podspec 目录，支持 `.h/.m/.mm`。作者、homepage、source、许可为待填写的发布元数据；本地 `:path` 不下载示例 URL，也不代表可以直接发布。不要把实际用户的仓库、私钥或账号固化进通用模板。
