# MonkeyDev

> **使用 AI 安装或操作 MonkeyDev：请先读取 [SKILL.md](SKILL.md)**，按其中的安装、使用流程和注意事项执行。可以直接将该文件链接提供给 AI。

MonkeyDev 基于 iOSOpenDev，为 Xcode 提供 MonkeyApp 模板，用于向已有 iOS App 注入 dylib、开发 Objective-C / Logos Hook，并使用 Xcode 重签名、安装和调试。

当前支持 **Apple Silicon Mac 和 iOS 15+ 非越狱 iPhoneOS arm64 真机**。已用内置 Demo 和未加密 App 验证构建、重复安装、Hook、符号断点、头文件导出及 Reveal。验证环境为 Xcode 27.0（27A266a）、iPhone 14 Pro / iOS 18.6.2。

## 安装

需要完整 Xcode、原生 arm64 shell，以及当前用户的 `~/theos`。发行包已包含原生 monkeyparser 和 class-dump，正常安装无需自行编译这些工具。

先以普通用户安装 Theos，不要将其安装到 `/opt/theos`：

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/theos/theos/master/bin/install-theos)"
```

首次安装：

```bash
sudo /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/AloneMonkey/MonkeyDev/master/bin/md-install)"
/opt/MonkeyDev/bin/md-doctor
```

后续更新：

```bash
sudo /opt/MonkeyDev/bin/md-update
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

1. 安装后保存工作并重启 Xcode，通过 **File → New → Project → MonkeyDev → MonkeyApp** 新建工程。
2. 填写项目名称、开发团队和 Organization Identifier。`Target App` 保持 `Optional`。
3. 将一个已砸壳的 IPA 或未加密 `.app` 放入 `<App target>/TargetApp/`，保持只有一份目标输入。不放输入时使用内置 Demo；无需设置 `MONKEYDEV_INPUT_APP`。
4. 选择 iPhone，以 Debug Build/Run。签名需要当前团队可用的证书、匹配的描述文件及设备授权。

`Target App` 文本框是历史越狱 Frida/SSH dump 入口，不是 IPA 路径选择器；该入口未纳入当前验证范围。使用上述 TargetApp 文件夹放入未加密输入，MonkeyDev 不负责在非越狱设备上自动砸壳。

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

## 越狱 Logos Tweak

Logos Tweak 支持选择 rootless / rootful 包布局，使用设备上兼容 MobileSubstrate 接口的 Hook 框架（例如 ElleKit）。不需要随插件打包旧 Substrate。rootless 已在越狱真机验证，rootful 当前完成构建和包内容检查。

CaptainHook Tweak 和 Command-line Tool 使用相同的 USB、认证和 deb 安装配置。CaptainHook 默认使用内部 Objective-C Runtime Hook，不链接 Substrate；仍需设备上的 tweak 加载器加载插件。将工程 `Package/Library/MobileSubstrate/DynamicLibraries/<项目名>.plist` 的 Filter 改为目标 App 的 Bundle ID。

Command-line Tool 保留 C、C++、Foundation、Core Foundation 类型，使用 ldid 签名，默认不申请额外权限。rootless 安装到 `/var/jb/usr/bin`，rootful 安装到 `/usr/bin`；安装后通过设备 SSH 执行程序，不通过 Xcode Run 启动。

创建向导默认使用 USB 连接和 rootless 布局，授权方式可选 `None`、`KEY`（默认，SSH 密钥免密）或 `PASSWORD`（输入设备账号、密码）。`None` 只生成 deb，不安装；`KEY` 和 `PASSWORD` 在 Build 后自动安装 tweak。免密模式沿用 SSH 配置；只有密码模式启用账号、密码输入，默认账号为 `mobile`，密码必填。向导填写的密码会保存在工程中，请勿提交或分享。

USB 优先使用显式配置的 UDID，其次使用 Xcode 选择的设备，否则自动识别唯一连接的 USB 设备。IP 连接、SSH 别名和其他高级设置仍可在 target 的 Build Settings 中配置：

| 设置 | 用途 |
| --- | --- |
| `MonkeyDevConnectionType` | `USB`：通过 inetcat 直连；`IP`：通过局域网直连；`SSH`：继承 SSH 配置别名 |
| `MonkeyDevDeviceUDID` | 可选，手动指定 USB 目标设备；连接多台设备时可填写 |
| `MonkeyDevDeviceIP` | IP 地址或 SSH 别名；USB 模式也可填写别名以复用账号和密钥配置 |
| `MonkeyDevDevicePort` | 设备 SSH 端口；USB 默认 22，SSH 别名模式留空可继承配置 |
| `MonkeyDevAuthentication` | `None`：只打包、不安装；`AUTO`：自动认证；`KEY`：公钥免密；`PASSWORD`：强制密码认证 |
| `MonkeyDevDeviceUser` | SSH 用户，留空继承 `~/.ssh/config` |
| `MonkeyDevDeviceKey` | 可选私钥路径，留空使用 SSH 配置或 ssh-agent |
| `MonkeyDevDevicePasswordFile` | 可选本地密码文件（一行密码），用于密码登录或非 root 用户的 sudo 安装 |
| `MonkeyDevInstallOnAnyBuild` | 设为 `YES` 后，Build 自动上传并安装 deb |
| `MonkeyDevkillProcessOnInstall` | 安装后退出的目标进程名，默认留空，不自动重启 SpringBoard |

USB 模式需要 `brew install libusbmuxd libimobiledevice`，无需启动 iproxy；密码认证需要 `brew install sshpass`。密码也可通过不提交 Git 的本地配置设置 `MonkeyDevDevicePassword`，或使用密码文件。密码文件与直接配置同时存在时，以密码文件为准。

首次连接先在终端确认设备 SSH 主机身份。USB 模式使用 `monkeydev-usb-<UDID>` 作为主机身份别名；IP 模式使用目标主机身份；SSH 模式遵循用户已有配置。构建不会关闭主机密钥检查。SSH 免密登录与 sudo 权限独立：mobile 免密登录后，安装 deb 仍需要 sudo 密码或已有的免密 sudo 权限。

首次 USB 连接可用下面的命令，将 `<UDID>` 和 `mobile` 替换为实际设备与账号；密钥可由 SSH 配置提供，也可通过 `-i` 指定：

```bash
ssh -o "ProxyCommand=inetcat -u <UDID> 22" -o "HostKeyAlias=monkeydev-usb-<UDID>" mobile@usb-iphone
```

## 支持范围与迁移

- 支持 MonkeyApp 的 thin arm64、未加密 iOS 真机输入；不支持 Intel 主机、模拟器、arm64e/PAC、Fat 或加密输入。arm64e 设备可以运行 arm64 App。
- 打包副本会移除 App 扩展、Watch 和旧 Store 元数据；当前不覆盖扩展的独立签名与安装。原始 IPA/App 保留。
- Cycript 和旧 Substrate 运行库已移除。CaptainHook/Logos internal 保留；Logos internal 不支持 `%hookf`。
- Logos Tweak、CaptainHook Tweak、iOS Command-line Tool 的 rootless arm64 已完成真机验证；rootful 仅完成构建和打包检查。
- macOS、MonkeyPod/CocoaPods 等历史模板尚未迁移验证，不在当前支持范围内。
- 模板更新影响新建项目；已有工程需单独迁移。增量构建的签名阶段必须每次执行。

历史资料保留在 [Wiki](https://github.com/AloneMonkey/MonkeyDev/wiki) 和 [MonkeyDevSpecs](https://github.com/AloneMonkey/MonkeyDevSpecs)，其中旧依赖和安装步骤不代表当前适配状态。

## 卸载

```bash
sudo /opt/MonkeyDev/bin/md-uninstall
```

卸载会删除整个 `/opt/MonkeyDev` 专用目录（包括自行放入其中的文件），以及安装器记录的模板链接和 shell 配置。需要保留的自定义文件请先备份；工程、目标 IPA/App 和 Theos 不会删除，也不会修改 Xcode.app。

**免责声明: 软件仅供技术交流，禁止用于商业及非法用途，如产生法律纠纷与本人无关。**

## 认识更多同行 · 新识 HiNexus

除了分享代码，也欢迎来我做的社群网站 [新识 HiNexus](https://hinexus.me) 认识更多有趣的人。

免费创建你的职业个人主页，展示经历、专业方向、能提供的帮助和正在寻找的合作，让志同道合的人更容易找到你。无论你关注移动安全、逆向工程、独立开发还是 AI，都欢迎来介绍自己、交流想法、寻找合作伙伴。

**[来新识，认识一下 →](https://hinexus.me)**

## 关注公众号 · 添加个人微信

欢迎扫码关注我的微信公众号，或添加个人微信，一起交流技术与实践。

| 个人微信 · AloneMonkey | 微信公众号 |
| :---: | :---: |
| <img src="assets/wechat-personal.jpg" alt="AloneMonkey 个人微信二维码" width="280" /> | <img src="assets/wechat-official-account.png" alt="微信公众号关注二维码" width="280" /> |
