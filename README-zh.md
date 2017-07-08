# MonkeyDev

[English Doc](README.md)
|
[中文文档](README-zh.md)

iOSOpenDev修改版。

* 安装更简单
* 支持最新版theos
* 支持CaptainHook Tweak、Logos Tweak、Command-line Tool

在最新的theos和Xcode 9测试正常。

### 准备

* 安装最新[theos](https://github.com/theos/theos/wiki)
* 安装 brew install ldid
* 设备免密码登录

```
ssh-keygen -t rsa -P ''
ssh-copy-id -i /Users/用户名/.ssh/id_rsa root@ip
```

### 安装

如果要对指定Xcode安装:

```
sudo xcode-select -s /Applications/Xcode-beta.app
```

默认:

```
xcode-select -p
```

安装：
```
git clone https://github.com/AloneMonkey/MonkeyDev.git
cd MonkeyDev/bin
sudo ./md-install
```

### 使用
新建项目，在iOS模板最下面可以找到`MonkeyDev`模板，已支持`CaptainHook Tweak`、`Logos Tweak`和`Command-line Tool`。

![image](http://7xtdl4.com1.z0.glb.clouddn.com/script_1499260720390.png)

`Logos Tweak`会自动链接`CydiaSubstrate`，不再需要手动链接。

`Commonand + B`编译，不安装，设置`MonkeyDevInstallOnAnyBuild`为`YES`，会自动打包安装到设备。

`Command + Shift + i`编译安装，但是这种方式是`Release`模式，看不到log输出。

在编译设置中可以自定义设备ip和ssh的端口:

![image](http://7xtdl4.com1.z0.glb.clouddn.com/script_1499525830459.png)

不设置的话，ip默认为`localhost`，port默认为`2222`。

当然你也可以在`~/.zshrc`或其它profile里面设置`MonkeyDevDeviceIP`和`MonkeyDevDevicePort`。

```
export MonkeyDevDeviceIP=
export MonkeyDevDevicePort=
```

查看log的会可以使用`idevicesyslog`查看，毕竟带颜色。。。。

### 设置说明

|设置项|意义|
|--|--|
|MonkeyDevBuildPackageOnAnyBuild|每次build都生成deb包|
|MonkeyDevCopyOnBuild|build的时将deb包拷贝到设备的/var/root/MonkeyDevBuilds/目录|
|MonkeyDevDeviceIP|目标设备的ip地址，默认USB连接，localhost|
|MonkeyDevDevicePort|目标设备的端口，默认2222|
|MonkeyDevInstallOnAnyBuild|每次build都将deb安装到设备|
|MonkeyDevInstallOnProfiling|点击Profile才将deb安装到设备|
|MonkeyDevRespringOnInstall|安装的时候重启SpringBoard|
|MonkeyDevUsePackageVersionPList|使用Supporting Files下面的PackageVersion.plist文件来指定deb版本|
|MonkeyDevPath|MonkeyDev的安装路径，默认的，不用修改|
|MonkeyDevTheosPath|theos的安装路径|

### 卸载

```
sudo ./md-uninstall
```

### 更新日志

v 1.0

* 增加CaptainHook Tweak、Logos Tweak、Command-line Tool
* 自动链接CydiaSubstrate.framwork
* 默认设备ip和端口