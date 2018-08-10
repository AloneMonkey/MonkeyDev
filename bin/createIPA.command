#!/bin/bash
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ ${DIR} = "/opt/MonkeyDev/bin" ]]; then 
	DIR="$PWD"
fi

function run {
	echo "Executing command: $@"
	$@
	if [[ $? != "0" ]]; then
		echo "Executing the above command has failed!"
		exit 1
	fi
}

function run_at {
	pushd $1
	shift
	run $@
	popd
}

echo "==================MonkeyDev(create ipa file...)=================="

run "rm -rf ${DIR}/Target.ipa ${DIR}/Payload"
run "mkdir ${DIR}/Payload"

APP=$(find ${DIR} -type d | grep ".app$" | head -n 1)

run "cp -rf ${APP} ${DIR}/Payload"
run_at ${DIR} "zip -qr Target.ipa Payload"
run "rm -rf ${DIR}/Payload"

echo "==================MonkeyDev(done)=================="

exit;