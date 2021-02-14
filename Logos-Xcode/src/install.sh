#!/bin/bash

#
# 	pr0crustes version.
#	Edited version of the work of Tiago Bastos and Alex Karahalios.
#	Last edited 15/9/2018
#

set -e

# Path were this script is located
Script_Path="/opt/MonkeyDev/Logos-Xcode/src"
# "$(dirname "$(realpath "$0")")"

# Checks if has enought permission
echo "Checking Permissions..."
if [ $EUID -ne 0 ]; then
	echo "$0 needs to be run as root."
	echo "	Check README for info."
	echo "	Aborting..."
	exit 2
fi

# Assumes Xcode 4+.
echo "Checking Xcode..."
XCODE_MAJOR_VERSION=`xcodebuild -version | awk 'NR == 1 {print int($2)}'`
if [ "$XCODE_MAJOR_VERSION" -lt "4" ]; then
	echo "Xcode 4+ not found."
	exit 1
fi

# Check if Logos.xclangspec is present in the same folder
echo "Finding Logos.xclangspec..."
if [ ! -f $Script_Path/Logos.xclangspec ]; then
	echo "Logos.xclangspec was not found."
	echo "You probably forgot to run 'python(3) xclangspec_generator.py'"
	exit 1
fi


echo "It's highly recommended that, if you are installing for the first time, you make a backup of the folder /Applications/Xcode.app/Contents/SharedFrameworks/DVTFoundation.framework/Versions/A/Resources"
while true; do
    read -p "Do you wish to continue? (Y)es, (N)o	" yn
    case $yn in
        [Yy]*) 
			# This framework is found withing the Xcode.app package and is used when Xcode is a monolithic install (all contained in Xcode.app)
			DVTFountain_Path="/Applications/Xcode.app/Contents/SharedFrameworks/DVTFoundation.framework/Versions/A/Resources/"

			# Backup
			cp "$DVTFountain_Path/DVTFoundation.xcplugindata" "$DVTFountain_Path/DVTFoundation.xcplugindata.bak"

			# Now merge in the additonal languages to DVTFoundation.xcplugindata
			echo "Merging..."
			/usr/libexec/PlistBuddy "$DVTFountain_Path/DVTFoundation.xcplugindata"  -c "Merge $Script_Path/AdditionalLanguages.plist plug-in:extensions"

			# Copy in the xclangspecs for the languages (assumes in same directory as this shell script)
			cp "$Script_Path/Logos.xclangspec" "$DVTFountain_Path"

			# Remove any cached Xcode plugins
			rm -rf /private/var/folders/*/*/*/com.apple.DeveloperTools/*/Xcode/PlugInCache.xcplugincache

			# Final message
			echo "Sucessfully Installed."
			echo "Syntax coloring must be manually selected from the Editor - Syntax Coloring menu in Xcode."
			exit 0
			;;
        [Nn]*) 
			echo "Exiting..."
			exit 1
			;;
        *) 
			;;
    esac
done
