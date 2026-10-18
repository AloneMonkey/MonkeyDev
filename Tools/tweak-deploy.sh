#!/bin/bash
# Install via SSH; ~/.ssh/config can provide USB ProxyCommand and key settings.
set -eo pipefail
fail() { echo "ERROR: $*" >&2; exit 1; }
[[ $# == 1 && -f "$1" ]] || fail "Usage: tweak-deploy.sh package.deb"
package="$1"
resolve_local_path() {
    local path="${1/#\~/$HOME}"
    [[ "$path" == /* ]] || path="${PROJECT_DIR:-$PWD}/$path"
    printf '%s\n' "$path"
}
if [[ -n "$MonkeyDevDevicePasswordFile" ]]; then
    MonkeyDevDevicePasswordFile="$(resolve_local_path "$MonkeyDevDevicePasswordFile")"
    [[ -f "$MonkeyDevDevicePasswordFile" && -r "$MonkeyDevDevicePasswordFile" ]] || fail "Cannot read device password file"
    MonkeyDevDevicePassword="$(cat "$MonkeyDevDevicePasswordFile")"
fi
host="${MonkeyDevDeviceIP:-localhost}"
port="${MonkeyDevDevicePort:-}"
[[ "$host" != -* && ( -z "$port" || "$port" =~ ^[0-9]+$ ) ]] || fail "Invalid SSH host or port"
connection="$(printf '%s' "${MonkeyDevConnectionType:-SSH}" | tr '[:lower:]' '[:upper:]')"
auth="$(printf '%s' "${MonkeyDevAuthentication:-AUTO}" | tr '[:lower:]' '[:upper:]')"
process="${MonkeyDevkillProcessOnInstall:-}"
[[ -z "$process" || "$process" =~ ^[A-Za-z0-9_.-]+$ ]] || fail "Invalid process name"
args=(-T -o ConnectTimeout=10)
[[ -z "$port" ]] || args+=(-p "$port")
case "$connection" in
    USB)
        udid="$MonkeyDevDeviceUDID"
        if [[ -z "$udid" && "${TARGET_DEVICE_IDENTIFIER:-}" =~ ^([0-9A-Fa-f]{40}|[0-9A-Fa-f]{8}-[0-9A-Fa-f]{16})$ ]]; then
            udid="$TARGET_DEVICE_IDENTIFIER"
        fi
        if [[ -z "$udid" ]]; then
            command -v idevice_id >/dev/null || fail "USB detection requires idevice_id: brew install libimobiledevice"
            devices="$(idevice_id -l)" || fail "Cannot enumerate USB devices"
            deviceCount="$(printf '%s\n' "$devices" | /usr/bin/awk 'NF {n++} END {print n+0}')"
            [[ "$deviceCount" == 1 ]] || fail "Connect one USB iPhone, select a device in Xcode, or set MonkeyDevDeviceUDID"
            udid="$(printf '%s\n' "$devices" | /usr/bin/awk 'NF {print; exit}')"
        fi
        [[ -n "$udid" && "$udid" =~ ^[A-Za-z0-9-]+$ ]] || fail "Set MonkeyDevDeviceUDID for USB installation"
        inetcat="$(command -v inetcat)" || fail "USB SSH requires inetcat: brew install libusbmuxd"
        printf -v proxy '%q ' "$inetcat" -u "$udid" "${port:-22}"
        args+=(-o "ProxyCommand=$proxy" -o "HostKeyAlias=monkeydev-usb-$udid")
        host="${MonkeyDevDeviceIP:-monkeydev-usb-$udid}"
        ;;
    IP)
        [[ -n "$MonkeyDevDeviceIP" ]] || fail "Set MonkeyDevDeviceIP for IP installation"
        args+=(-o ProxyCommand=none)
        ;;
    SSH) ;; # Inherit ProxyCommand, user, identity and port from ~/.ssh/config.
    *) fail "Unknown MonkeyDevConnectionType: $connection" ;;
esac
[[ -z "$MonkeyDevDeviceUser" ]] || args+=(-l "$MonkeyDevDeviceUser")
if [[ -n "$MonkeyDevDeviceKey" ]]; then
    key="$(resolve_local_path "$MonkeyDevDeviceKey")"
    [[ -f "$key" ]] || fail "SSH key not found: $key"
    args+=(-i "$key" -o IdentitiesOnly=yes)
fi
usePassword=NO
case "$auth" in
    AUTO) [[ -z "$MonkeyDevDevicePassword" ]] || usePassword=YES ;;
    KEY) args+=(-o PreferredAuthentications=publickey) ;;
    PASSWORD)
        [[ -n "$MonkeyDevDevicePassword" ]] || fail "Password authentication requires a device password"
        usePassword=YES
        args+=(-o PubkeyAuthentication=no -o PreferredAuthentications=password,keyboard-interactive)
        ;;
    *) fail "Unknown MonkeyDevAuthentication: $auth" ;;
esac
if [[ "$usePassword" == YES ]]; then
    command -v sshpass >/dev/null || fail "Password authentication requires sshpass; install it with brew install sshpass"
    args+=(-o BatchMode=no -o NumberOfPasswordPrompts=1)
else
    args+=(-o BatchMode=yes)
fi
ssh_device() {
    if [[ "$usePassword" == YES ]]; then
        SSHPASS="$MonkeyDevDevicePassword" sshpass -e ssh "${args[@]}" "$host" "$@"
    else
        ssh "${args[@]}" "$host" "$@"
    fi
}
# Do not disable host verification. Establish trust with an interactive SSH
# connection before building, so Xcode never waits for a prompt.
remote="$(ssh_device 'mktemp /tmp/monkeydev-tweak.XXXXXX')" || \
    fail "SSH failed. Connect manually first to verify the host and test authentication."
[[ "$remote" =~ ^/tmp/monkeydev-tweak\.[A-Za-z0-9]+$ ]] || fail "Unexpected upload path from device"
cleanup() { ssh_device "rm -f '$remote'" </dev/null >/dev/null 2>&1 || true; }
trap cleanup EXIT
ssh_device "cat > '$remote'" < "$package" || fail "Failed to upload tweak"
if [[ -n "$MonkeyDevDevicePassword" ]]; then
    install="if [ \"\$(id -u)\" = 0 ]; then dpkg -i '$remote'; else sudo -S -p '' dpkg -i '$remote'; fi"
    printf '%s\n' "$MonkeyDevDevicePassword" | ssh_device "$install" || fail "Package installation failed"
else
    ssh_device "if [ \"\$(id -u)\" = 0 ]; then dpkg -i '$remote'; else sudo -n dpkg -i '$remote'; fi" </dev/null || \
        fail "Package installation failed. Non-root accounts need passwordless sudo for dpkg, or configure the account password."
fi
if [[ -n "$process" ]]; then
    # Never interpret 'process not running' as an installation failure.
    ssh_device "killall '$process' >/dev/null 2>&1 || true" </dev/null
fi
echo "Installed tweak via $connection on $host:${port:-SSH-config}"
