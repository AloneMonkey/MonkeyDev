---
name: monkeydev
description: >-
  使用 MonkeyDev 在 Apple Silicon Mac 上创建 Xcode MonkeyApp 工程，为未加密 iOS App 注入 dylib、编写 CaptainHook/Logos Hook、重签名安装到非越狱 iPhone，并进行 LLDB 调试、OC 头文件导出、符号还原、Reveal 检查及方法追踪。
---

# MonkeyDev

使用 Xcode 完成已有 iOS App 的插件开发、重签名、真机安装与调试。工作流为：安装 MonkeyDev → 创建 MonkeyApp → 放入目标 IPA/App → 编写 dylib → Xcode Build/Run。优先使用已有工程；用户要求新建时再创建工程。不要将此流程替换成独立重打包脚本。

仓库：<https://github.com/AloneMonkey/MonkeyDev>。本文件可单独作为操作入口，无需先读取完整仓库文档。从分支或特定提交读取本文件时，使用同一版本的安装脚本和源码，避免新说明搭配旧模板。

## 1. 检查前提

- Apple Silicon Mac，使用原生 arm64 终端；完整 Xcode 已安装并完成首次启动配置。
- iPhone 开启开发者模式、信任此 Mac，并在安装启动时保持解锁。准备可用的开发团队、签名证书及授权该设备的 provisioning profile；Personal Team 的实际限制由 Xcode/Apple 决定。
- 输入为已砸壳的 IPA 或未加密 `.app`，主程序及保留的嵌入代码应符合 thin arm64 范围。MonkeyDev 不负责在非越狱设备上自动砸壳。
- 当前支持基线为 iOS 15+ 真机，不覆盖 Intel 主机、模拟器、Fat 输入、arm64e/PAC 或加密输入。设备 CPU 为 arm64e 不妨碍运行 arm64 App。

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

先确认符号能查到、断点有解析位置，再操作 App 触发相应路径。已解析却未命中可能只是调用了另一个重载或实现，不能直接判断符号还原失败。monkeyparser 负责 dylib 加载命令注入与独立的 OC 方法符号还原；系统 codesign 负责最终签名。

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
