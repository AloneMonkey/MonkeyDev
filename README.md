# MonkeyDev

MonkeyDev 基于 iOSOpenDev，为 Xcode 提供 MonkeyApp 模板，用于向已有 iOS App 注入 dylib、开发 Objective-C / Logos Hook，并使用 Xcode 重签名、安装和调试。

本轮适配面向 **Apple Silicon Mac 和非越狱 iPhoneOS arm64 真机**。已用内置 Demo 和用户提供的未加密 App 验证构建、重复安装、Hook、符号断点、头文件导出及 Reveal。验收环境为 Xcode 27.0（27A266a）、iPhone 14 Pro / iOS 18.6.2。

## 安装

需要完整 Xcode、原生 arm64 shell，以及当前用户的 `~/theos`。发行包已包含原生 monkeyparser 和 class-dump，正常安装无需自行编译这些工具。

先以普通用户安装 Theos，不要将其安装到 `/opt/theos`：

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/theos/theos/master/bin/install-theos)"
```

安装和更新：

```bash
sudo /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/AloneMonkey/MonkeyDev/master/bin/md-install)"
sudo /opt/MonkeyDev/bin/md-update
/opt/MonkeyDev/bin/md-doctor
```

开发时，也可在 MonkeyDev 源码目录安装或更新本地版本：

```bash
sudo env MONKEYDEV_SOURCE_DIR="$PWD" /bin/bash bin/md-install
# 本地更新仍指定源码目录：
sudo env MONKEYDEV_SOURCE_DIR="$PWD" /bin/bash bin/md-update
/opt/MonkeyDev/bin/md-doctor
```

macOS 原有 `/bin/sh -c` 入口也已验证兼容。安装位置为 `/opt/MonkeyDev`，模板注册在当前用户的 Xcode 模板目录；安装、更新和卸载不修改 Xcode.app。安装器先准备并校验完整版本，再替换安装，生成版本回执和文件哈希。完整模板统一维护在 [MonkeyDev-Xcode-Templates](https://github.com/AloneMonkey/MonkeyDev-Xcode-Templates)，安装时直接复制，不再应用模板补丁。

## 创建并运行 MonkeyApp

1. 安装后保存工作并重启 Xcode，选择 **MonkeyDev → MonkeyApp**。
2. 填写项目名称、开发团队和 Organization Identifier。`Target App` 保持 `Optional`。
3. 将一个已砸壳的 IPA 或未加密 `.app` 放入 `<App target>/TargetApp/`。不放输入时使用内置 Demo；无需设置 `MONKEYDEV_INPUT_APP`。
4. 选择 iPhone，以 Debug Build/Run。签名需要当前团队可用的证书、匹配的描述文件及设备授权。

`Target App` 文本框保留的是旧越狱 Frida/SSH 自动 dump 入口，这轮未重新验证该流程；它不能让普通非越狱设备直接砸壳。当前验收路径是手动放入未加密输入。

创建向导提供以下 YES/NO 下拉框；创建后仍可在 **App target → Build Settings → User-Defined** 修改：

| 选项 | Build Setting | 默认 |
| --- | --- | --- |
| Inject Dylib | `MONKEYDEV_INSERT_DYLIB` | YES |
| Keep Original Bundle ID | `MONKEYDEV_DEFAULT_BUNDLEID` | NO |
| Restore OC Symbols | `MONKEYDEV_RESTORE_SYMBOL` | NO |
| Export OC Headers | `MONKEYDEV_CLASS_DUMP` | NO |
| Reveal (Debug) | `MONKEYDEV_REVEAL` | NO |

默认使用项目 Bundle ID。保留原 Bundle ID 仍需要描述文件授权该 ID，开关不会绕过签名权限。最小运行时固定开启，不捆绑旧 Substrate/Cycript。

## 编写 Hook 与调试

- `<项目名>Dylib/<项目名>Dylib.m`：普通 Objective-C / CaptainHook 示例，使用内部 runtime 后端。
- `<项目名>Dylib/Logos/<项目名>Dylib.xm`：Logos 示例，采用 internal 后端；生成的 `.mm` 同时参与编译，编辑源文件 `.xm`，不要手改 `.mm`。
- 两个入口可以同时执行。正式模板只打印示例日志，不自动弹窗；Trace 不自动注册业务方法。

源码断点直接设在 dylib 的实际语句上。分析输入 App 的 OC 方法时，可开启符号还原，重新构建后在 LLDB 设置符号断点：

```lldb
breakpoint set -n '-[YourClass yourMethod:]'
```

将类名和 selector 换成目标 App 的实际方法。基础 UI/runtime 查询位于 `Tools/LLDBTools.h/.mm`，方法追踪位于 `Trace/MDMethodTrace.h/.mm`，均仅 Debug 可用。Trace 输出调用编号、线程号、嵌套深度、参数、返回值及同步方法耗时；它只支持明确的签名子集，不是任意 ABI 的通用 Hook。

更多使用方法和调试命令见 [SKILL.md](SKILL.md)。

## 头文件与 Reveal

开启 **Export OC Headers** 后，构建将主程序头文件导出到可见目录：

```text
<工程目录>/Headers/<App target 名>/
```

构建日志会打印实际路径。头文件不会自动加入 Xcode 的 App target；生成目录应加入项目 `.gitignore`。旧版本曾使用 `.monkeydev/Headers`，现有工程下次构建使用新目录。头文件主要用于分析，不保证能作为完整 SDK 直接编译。

Reveal 使用用户本机 SDK，不再随 MonkeyDev 分发框架。先通过 Reveal 下载 SDK，默认读取：

```text
~/Library/Application Support/Reveal/RevealServer/RevealServer.xcframework
```

开启 **Reveal (Debug)** 后重新 Build/Run，允许 App 的本地网络访问，在 Reveal 选择运行中的 App；USB 连接已验证。查看层级时保持 App 继续运行，不停在断点上。Release 不接入 Reveal。

## 支持范围与迁移

- 当前验收重点是 MonkeyApp 的 thin arm64、未加密 iOS 真机输入；不支持 Intel 主机、模拟器、arm64e/PAC、Fat 或加密输入。
- 打包副本会移除 App 扩展、Watch 和旧 Store 元数据；当前不覆盖扩展的独立签名与安装。原始 IPA/App 保留。
- Cycript 和旧 Substrate 运行库已移除。CaptainHook/Logos internal 保留；Logos internal 不支持 `%hookf`。
- macOS、越狱 tweak、旧 Command-line Tool、MonkeyPod/CocoaPods 等历史模板仍需单独迁移验证，不作为本轮已支持功能。
- 模板更新影响新建项目；已有工程需单独迁移。增量构建的签名阶段必须每次执行。

历史资料保留在 [Wiki](https://github.com/AloneMonkey/MonkeyDev/wiki) 和 [MonkeyDevSpecs](https://github.com/AloneMonkey/MonkeyDevSpecs)，其中旧依赖和安装步骤不代表当前适配状态。

**免责声明: 软件仅供技术交流，禁止用于商业及非法用途，如产生法律纠纷与本人无关。**

<br>

<h2>《iOS应用逆向与安全》出版啦！！！</h2>

# 购书链接

#### 京东: [https://item.jd.com/12361729.html](https://item.jd.com/12361729.html)

#### 天猫: [https://detail.tmall.com/item.htm?id=570691214072](https://detail.tmall.com/item.htm?id=570691214072)

#### 当当: [http://product.dangdang.com/25283164.html](http://product.dangdang.com/25283164.html)

#### 亚马逊: [https://www.amazon.cn/dp/B07D5952BR/](https://www.amazon.cn/dp/B07D5952BR/)

<h3>请大家多多支持正版哦~</h3>
