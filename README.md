# MonkeyDev

[English Doc](README.md)
|
[中文文档](README-zh.md)

A modified version of iOSOpenDev

* easy to install
* support the latest version of theos
* support CaptainHook Tweak、Logos Tweak、Command-line Tool

run with the latest theos and Xcode 9 is ok。

### Requirements

* Install the latest [theos](https://github.com/theos/theos/)
* brew install ldid
* SSH into your jailbroken iDevice without a password

```
ssh-keygen -t rsa -P ''
ssh-copy-id -i /Users/username/.ssh/id_rsa root@ip
```

### Installation

select the Xcode to install:

```
sudo xcode-select -s /Applications/Xcode-beta.app
```

default Xcode to install:

```
xcode-select -p
```

install:

```
git clone https://github.com/AloneMonkey/MonkeyDev.git
cd MonkeyDev/bin
sudo ./md-install
```

### Usage

Create a new project, Select a template to start。

![image](http://7xtdl4.com1.z0.glb.clouddn.com/script_1499260720390.png)

Compile: `Commonand + B`

Install: 

* set `MonkeyDevInstallOnAnyBuild` to `YES`， then `Commonand + B` with `Debug`
* `Command + Shift + i` with `Release`， disable log print

Custom Build Settings:

![image](http://7xtdl4.com1.z0.glb.clouddn.com/script_1498661304679.png)

default value:
ip: `localhost`
port: `2222`

The Bash profile file also can export variable。

`~/.zshrc` or ` ~/.bash_profile` or others.

```
export MonkeyDevDeviceIP=
export MonkeyDevDevicePort=
```

use `idevicesyslog` to show log print.

### Custom Settings

|setting|meaning|
|--|--|
|MonkeyDevBuildPackageOnAnyBuild|create package on any type of build. |
|MonkeyDevCopyOnBuild|during any build, copy the target (executable) to the device at /var/root/iOSOpenDevBuilds/|
|MonkeyDevDeviceIP|the host name (e.g. MyiPhone.local) or IP address (e.g. 192.168.1.101) of the device you wish to use during development.|
|MonkeyDevDevicePort|connect port of the device|
|MonkeyDevInstallOnAnyBuild|install the package on the device on any type of build. |
|MonkeyDevInstallOnProfiling|during a Build For Profiling (Command-Shift-I or Product > Build For > Build For Profiling), build the project's Debian package, copy the package to the device at /var/root/MonkeyDevPackages (using SSH) and install the package (using SSH and running dpkg locally on the device)|
|MonkeyDevRespringOnInstall|after the Debian package has been built and installed, respring (i.e. kill and relaunch SpringBoard) the device.|
|MonkeyDevUsePackageVersionPList|It indicates whether to use the target's PackageVersion.plist file to set the Debian package's control file's Version field only. |
|MonkeyDevPath|Do not change this. This is the path to MonkeyDev which is used by other build settings.|
|MonkeyDevTheosPath|the path to theos installed|

### uninstall

```
sudo ./md-uninstall
```

### changelog

v 1.0

* add CaptainHook Tweak、Logos Tweak、Command-line Tool support
* auto link CydiaSubstrate.framwork
* set default value to device ip and port