MONKEYDEV_PATH="/opt/MonkeyDev"

# temp path
TEMP_PATH="${SRCROOT}/${TARGET_NAME}/tmp"

# monkeyparser
MONKEYPARSER="${MONKEYDEV_PATH}/bin/monkeyparser"

# create ipa script
CREATE_IPA="${MONKEYDEV_PATH}/bin/createIPA.command"

# build app path
BUILD_APP_PATH="${BUILT_PRODUCTS_DIR}/${TARGET_NAME}.app"

# default demo app
DEMOTARGET_APP_PATH="${MONKEYDEV_PATH}/Resource/TargetApp.app"

# link framework path
FRAMEWORKS_TO_INJECT_PATH="${MONKEYDEV_PATH}/Frameworks/"

# target app placed
TARGET_APP_PUT_PATH="${SRCROOT}/${TARGET_NAME}/TargetApp"

# Compatiable old version
MONKEYDEV_INSERT_DYLIB=${MONKEYDEV_INSERT_DYLIB:=YES}
MONKEYDEV_TARGET_APP=${MONKEYDEV_TARGET_APP:=Optional}
MONKEYDEV_ADD_SUBSTRATE=${MONKEYDEV_ADD_SUBSTRATE:=YES}
MONKEYDEV_DEFAULT_BUNDLEID=${MONKEYDEV_DEFAULT_BUNDLEID:=NO}

function isRelease() {
	if [[ "${CONFIGURATION}" = "Release" ]]; then
		true
	else
		false
	fi
}

function panic() { # args: exitCode, message...
	local exitCode=$1
	set +e
	
	shift
	[[ "$@" == "" ]] || \
		echo "$@" >&2

	exit ${exitCode}
}

function checkApp(){
	local TARGET_APP_PATH="$1"

	# remove Plugin an Watch
	rm -rf "${TARGET_APP_PATH}/PlugIns" || true
	rm -rf "${TARGET_APP_PATH}/Watch" || true

	/usr/libexec/PlistBuddy -c 'Delete UISupportedDevices' "${TARGET_APP_PATH}/Info.plist" 2>/dev/null

	VERIFY_RESULT=`export MONKEYDEV_CLASS_DUMP=${MONKEYDEV_CLASS_DUMP};MONKEYDEV_RESTORE_SYMBOL=${MONKEYDEV_RESTORE_SYMBOL};"$MONKEYPARSER" verify -t "${TARGET_APP_PATH}" -o "${SRCROOT}/${TARGET_NAME}"`

	if [[ $? -eq 16 ]]; then
	  	panic 1 "${VERIFY_RESULT}"
	else
	  	echo "${VERIFY_RESULT}"
	fi
}

function pack(){
	TARGET_INFO_PLIST=${SRCROOT}/${TARGET_NAME}/Info.plist
	# environment
	CURRENT_EXECUTABLE=$(/usr/libexec/PlistBuddy -c "Print CFBundleExecutable" "${TARGET_INFO_PLIST}" 2>/dev/null)

	# create tmp dir
	rm -rf "${TEMP_PATH}" || true
	mkdir -p "${TEMP_PATH}" || true

	# latestbuild
	ln -fhs "${BUILT_PRODUCTS_DIR}" "${PROJECT_DIR}"/LatestBuild
	cp -rf "${CREATE_IPA}" "${PROJECT_DIR}"/LatestBuild/

	# deal ipa or app
	TARGET_APP_PATH=$(find "${SRCROOT}/${TARGET_NAME}" -type d | grep "\.app$" | head -n 1)
	TARGET_IPA_PATH=$(find "${SRCROOT}/${TARGET_NAME}" -type f | grep "\.ipa$" | head -n 1)

	if [[ ${TARGET_APP_PATH} ]]; then
		cp -rf "${TARGET_APP_PATH}" "${TARGET_APP_PUT_PATH}"
	fi

	if [[ ! ${TARGET_APP_PATH} ]] && [[ ! ${TARGET_IPA_PATH} ]] && [[ ${MONKEYDEV_TARGET_APP} != "Optional" ]]; then
		echo "pulling decrypted ipa from jailbreak device......."
		PYTHONIOENCODING=utf-8 ${MONKEYDEV_PATH}/bin/dump.py ${MONKEYDEV_TARGET_APP} -o "${TARGET_APP_PUT_PATH}/TargetApp.ipa" || panic 1 "dump.py error"
		TARGET_IPA_PATH=$(find "${TARGET_APP_PUT_PATH}" -type f | grep "\.ipa$" | head -n 1)
	fi

	if [[ ! ${TARGET_APP_PATH} ]] && [[ ${TARGET_IPA_PATH} ]]; then
		unzip -oqq "${TARGET_IPA_PATH}" -d "${TEMP_PATH}"
		cp -rf "${TEMP_PATH}/Payload/"*.app "${TARGET_APP_PUT_PATH}"
	fi
	
	if [ -f "${BUILD_APP_PATH}/embedded.mobileprovision" ]; then
		mv "${BUILD_APP_PATH}/embedded.mobileprovision" "${BUILD_APP_PATH}"/..
	fi

	TARGET_APP_PATH=$(find "${TARGET_APP_PUT_PATH}" -type d | grep "\.app$" | head -n 1)

	if [[ -f "${TARGET_APP_PUT_PATH}"/.current_put_app ]]; then
		if [[ $(cat ${TARGET_APP_PUT_PATH}/.current_put_app) !=  "${TARGET_APP_PATH}" ]]; then
			rm -rf "${BUILD_APP_PATH}" || true
		 	mkdir -p "${BUILD_APP_PATH}" || true
		 	rm -rf "${TARGET_APP_PUT_PATH}"/.current_put_app
			echo "${TARGET_APP_PATH}" >> "${TARGET_APP_PUT_PATH}"/.current_put_app
		fi
	fi

	COPY_APP_PATH=${TARGET_APP_PATH}

	if [[ "${TARGET_APP_PATH}" = "" ]]; then
		COPY_APP_PATH=${DEMOTARGET_APP_PATH}
		cp -rf "${COPY_APP_PATH}/" "${BUILD_APP_PATH}/"
		checkApp "${BUILD_APP_PATH}"
	else
		checkApp "${COPY_APP_PATH}"
		cp -rf "${COPY_APP_PATH}/" "${BUILD_APP_PATH}/"
	fi

	if [ -f "${BUILD_APP_PATH}/../embedded.mobileprovision" ]; then
		mv "${BUILD_APP_PATH}/../embedded.mobileprovision" "${BUILD_APP_PATH}"
	fi

	# get target info
	ORIGIN_BUNDLE_ID=$(/usr/libexec/PlistBuddy -c "Print CFBundleIdentifier"  "${COPY_APP_PATH}/Info.plist" 2>/dev/null)
	TARGET_EXECUTABLE=$(/usr/libexec/PlistBuddy -c "Print CFBundleExecutable"  "${COPY_APP_PATH}/Info.plist" 2>/dev/null)

	if [[ ${CURRENT_EXECUTABLE} != ${TARGET_EXECUTABLE} ]]; then
		cp -rf "${COPY_APP_PATH}/Info.plist" "${TARGET_INFO_PLIST}"
	fi

	TARGET_DISPLAY_NAME=$(/usr/libexec/PlistBuddy -c "Print CFBundleDisplayName" "${TARGET_INFO_PLIST}" 2>/dev/null)

	# copy default framewrok
	TARGET_APP_FRAMEWORKS_PATH="${BUILD_APP_PATH}/Frameworks/"

	if [ ! -d "${TARGET_APP_FRAMEWORKS_PATH}" ]; then
		mkdir -p "${TARGET_APP_FRAMEWORKS_PATH}"
	fi

	if [[ ${MONKEYDEV_INSERT_DYLIB} == "YES" ]];then
		cp -rf "${BUILT_PRODUCTS_DIR}/lib""${TARGET_NAME}""Dylib.dylib" "${TARGET_APP_FRAMEWORKS_PATH}"
		cp -rf "${FRAMEWORKS_TO_INJECT_PATH}" "${TARGET_APP_FRAMEWORKS_PATH}"
		if [[ ${MONKEYDEV_ADD_SUBSTRATE} != "YES" ]];then
			rm -rf "${TARGET_APP_FRAMEWORKS_PATH}/libsubstrate.dylib"
		fi
		if isRelease; then
			rm -rf "${TARGET_APP_FRAMEWORKS_PATH}"/RevealServer.framework
			rm -rf "${TARGET_APP_FRAMEWORKS_PATH}"/libcycript*
		fi
	fi

	if [[ -d "$SRCROOT/${TARGET_NAME}/Resources" ]]; then
	 for file in "$SRCROOT/${TARGET_NAME}/Resources"/*; do
	 	extension="${file#*.}"
	  	filename="${file##*/}"
	  	if [[ "$extension" == "storyboard" ]]; then
	  		ibtool --compile "${BUILD_APP_PATH}/$filename"c "$file"
	  	else
	  		cp -rf "$file" "${BUILD_APP_PATH}/"
	  	fi
	 done
	fi

	# Inject the Dynamic Lib
	APP_BINARY=`plutil -convert xml1 -o - ${BUILD_APP_PATH}/Info.plist | grep -A1 Exec | tail -n1 | cut -f2 -d\> | cut -f1 -d\<`

	if [[ ${MONKEYDEV_INSERT_DYLIB} == "YES" ]];then
		"$MONKEYPARSER" install -c load -p "@executable_path/Frameworks/lib""${TARGET_NAME}""Dylib.dylib" -t "${BUILD_APP_PATH}/${APP_BINARY}"
		"$MONKEYPARSER" unrestrict -t "${BUILD_APP_PATH}/${APP_BINARY}"

		chmod +x "${BUILD_APP_PATH}/${APP_BINARY}"
	fi

	# Update Info.plist for Target App
	if [[ "${TARGET_DISPLAY_NAME}" != "" ]]; then
		for file in `ls "${BUILD_APP_PATH}"`;
		do
			extension="${file#*.}"
		    if [[ -d "${BUILD_APP_PATH}/$file" ]]; then
				if [[ "${extension}" == "lproj" ]]; then
					if [[ -f "${BUILD_APP_PATH}/${file}/InfoPlist.strings" ]];then
						/usr/libexec/PlistBuddy -c "Set :CFBundleDisplayName ${TARGET_DISPLAY_NAME}" "${BUILD_APP_PATH}/${file}/InfoPlist.strings"
					fi
		    	fi
			fi
		done
	fi

	if [[ ${MONKEYDEV_DEFAULT_BUNDLEID} = NO ]];then 
		/usr/libexec/PlistBuddy -c "Set :CFBundleIdentifier ${PRODUCT_BUNDLE_IDENTIFIER}" "${TARGET_INFO_PLIST}"
	else
		/usr/libexec/PlistBuddy -c "Set :CFBundleIdentifier ${ORIGIN_BUNDLE_ID}" "${TARGET_INFO_PLIST}"
	fi

	/usr/libexec/PlistBuddy -c "Delete :CFBundleIconFiles" "${TARGET_INFO_PLIST}"
	/usr/libexec/PlistBuddy -c "Add :CFBundleIconFiles array" "${TARGET_INFO_PLIST}"
	/usr/libexec/PlistBuddy -c "Add :CFBundleIconFiles: string ${TARGET_NAME}/icon.png" "${TARGET_INFO_PLIST}"

	cp -rf "${TARGET_INFO_PLIST}" "${BUILD_APP_PATH}/Info.plist"

	#cocoapods
	if [[ -f "${SRCROOT}/Pods/Target Support Files/Pods-""${TARGET_NAME}""Dylib/Pods-""${TARGET_NAME}""Dylib-frameworks.sh" ]]; then
		source "${SRCROOT}/Pods/Target Support Files/Pods-""${TARGET_NAME}""Dylib/Pods-""${TARGET_NAME}""Dylib-frameworks.sh"
	fi

	if [[ -f "${SRCROOT}/Pods/Target Support Files/Pods-""${TARGET_NAME}""Dylib/Pods-""${TARGET_NAME}""Dylib-resources.sh" ]]; then
		source "${SRCROOT}/Pods/Target Support Files/Pods-""${TARGET_NAME}""Dylib/Pods-""${TARGET_NAME}""Dylib-resources.sh"
	fi

	if [[ -f "${SRCROOT}/../Pods/Target Support Files/Pods-""${TARGET_NAME}""Dylib/Pods-""${TARGET_NAME}""Dylib-frameworks.sh" ]]; then
		source "${SRCROOT}/../Pods/Target Support Files/Pods-""${TARGET_NAME}""Dylib/Pods-""${TARGET_NAME}""Dylib-frameworks.sh"
	fi

	if [[ -f "${SRCROOT}/../Pods/Target Support Files/Pods-""${TARGET_NAME}""Dylib/Pods-""${TARGET_NAME}""Dylib-resources.sh" ]]; then
		source "${SRCROOT}/../Pods/Target Support Files/Pods-""${TARGET_NAME}""Dylib/Pods-""${TARGET_NAME}""Dylib-resources.sh"
	fi
}

if [[ "$1" == "codesign" ]]; then
	${MONKEYPARSER} codesign -i "${EXPANDED_CODE_SIGN_IDENTITY}" -t "${BUILD_APP_PATH}"
	if [[ ${MONKEYDEV_INSERT_DYLIB} == "NO" ]];then
		rm -rf "${BUILD_APP_PATH}/Frameworks/lib${TARGET_NAME}Dylib.dylib"
	fi
else
	pack
fi
