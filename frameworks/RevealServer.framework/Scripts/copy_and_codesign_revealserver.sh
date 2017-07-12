#!/usr/bin/env bash
set -o errexit
set -o nounset

# Ensure that we have a valid OTHER_LDFLAGS environment variable
OTHER_LDFLAGS=${OTHER_LDFLAGS:=""}

# Ensure that we have a valid REVEAL_SERVER_FILENAME environment variable
REVEAL_SERVER_FILENAME=${REVEAL_SERVER_FILENAME:="RevealServer.framework"}

# Ensure that we have a valid REVEAL_SERVER_PATH environment variable
REVEAL_SERVER_PATH=${REVEAL_SERVER_PATH:="${SRCROOT}/${REVEAL_SERVER_FILENAME}"}

# The path to copy the framework to
app_frameworks_dir="${CODESIGNING_FOLDER_PATH}/Frameworks"

copy_library() {
  mkdir -p "$app_frameworks_dir"
  cp -vRf "$REVEAL_SERVER_PATH" "${app_frameworks_dir}/"
}

codesign_library() {
  if [ -n "${EXPANDED_CODE_SIGN_IDENTITY}" ]; then
    codesign -fs "${EXPANDED_CODE_SIGN_IDENTITY}" "${app_frameworks_dir}/${REVEAL_SERVER_FILENAME}"
  fi
}

main() {
  if  [[ $OTHER_LDFLAGS =~ "RevealServer" ]]; then
    if [ -e "$REVEAL_SERVER_PATH" ]; then
      copy_library
      codesign_library
      echo "${REVEAL_SERVER_FILENAME} is included in this build, and has been copied to $CODESIGNING_FOLDER_PATH"
    else
      echo "${REVEAL_SERVER_FILENAME} is not included in this build, as it could not be found at $REVEAL_SERVER_PATH"
    fi
  else
    echo "${REVEAL_SERVER_FILENAME} is not included in this build because RevealServer was not present in the OTHER_LDFLAGS environment variable."
  fi
}

main
