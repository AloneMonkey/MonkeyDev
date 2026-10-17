#!/bin/bash
set -eo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ "$DIR" == /opt/MonkeyDev/bin ]]; then DIR="$PWD"; fi

# Export only a top-level build product, never an embedded or cached App.
apps=()
for app in "$DIR/"*.app; do
    [[ ! -d "$app" ]] || apps+=("$app")
done
[[ ${#apps[@]} == 1 ]] || { echo "ERROR: Expected exactly one App in $DIR" >&2; exit 1; }

# Keep existing exports and user-owned Payload directories intact on failure.
work="$(mktemp -d "$DIR/.monkeydev-export.XXXXXX")"
trap 'rm -rf "$work"' EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM
mkdir -p "$work/Payload/${apps[0]##*/}"
cp -pR "${apps[0]}/." "$work/Payload/${apps[0]##*/}/"
(cd "$work" && /usr/bin/zip -qry Target.ipa Payload)
mv -f "$work/Target.ipa" "$DIR/Target.ipa"
echo "Created IPA: $DIR/Target.ipa"
