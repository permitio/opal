#!/usr/bin/env bash
# fetch-tool.sh <name> downloads the release binary <name> that .github/binaries.lock pins for this
# machine, checks its sha256 before it unpacks anything, and installs it as bin/<name> at the
# repository root. It prints the installed path on stdout and its progress on stderr. The download
# stays in a temporary directory under RUNNER_TEMP (or TMPDIR), which the runner or the system
# clears.
#
# Exit codes: 0 when the binary is installed; 2 when the lock is missing, has no complete entry
# for the name or this platform, bin/<name> exists and is not a regular file, the download fails,
# the sha256 does not match, or the binary cannot be unpacked or installed. Nothing is unpacked
# or installed unless the sha256 matches, and the script never runs what it downloads.
set -euo pipefail

fail() {
  echo "fetch-tool: $*" >&2
  exit 2
}

[[ $# -eq 1 ]] || fail "usage: fetch-tool.sh <name>"
name=$1
name_re='^[A-Za-z0-9][A-Za-z0-9._-]*$'
[[ $name =~ $name_re ]] || fail "\"$name\" is not a tool name"

root=$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
lock_name=.github/binaries.lock
lock=$root/$lock_name
[[ -f $lock && -r $lock ]] || fail "$lock_name is missing or not readable"

case "$(uname -s)" in
Darwin) os=darwin ;;
Linux) os=linux ;;
*) fail "unsupported OS $(uname -s); $lock_name has darwin and linux binaries" ;;
esac
case "$(uname -m)" in
x86_64 | amd64) arch=amd64 ;;
arm64 | aarch64) arch=arm64 ;;
*) fail "unsupported architecture $(uname -m); $lock_name has amd64 and arm64 binaries" ;;
esac
platform=$os/$arch

# The values of the entry for $name. The sha256 sums are read by name in the checks below.
version='' url='' archive='' binary='' os_name='' arch_name=''
# shellcheck disable=SC2034 # set by set_key and read through ${!var}
sha_darwin_arm64='' sha_darwin_amd64='' sha_linux_amd64='' sha_linux_arm64=''

# set_key sets the variable named $1 to $2, and fails when the entry set it before.
set_key() {
  [[ -z ${!1} ]] || fail "$lock_name:$line_no: $key is set twice in [$name]"
  printf -v "$1" '%s' "$2"
}

comment_re='^[[:space:]]*(#.*)?$'
block_re='^\[([^]]+)\]$'
key_re='^([^[:space:]=]+)[[:space:]]*=[[:space:]]*(.*[^[:space:]])[[:space:]]*$'
found=false
block=''
line_no=0
while IFS= read -r line || [[ -n $line ]]; do
  line_no=$((line_no + 1))
  if [[ $line =~ $comment_re ]]; then
    continue
  fi
  if [[ $line =~ $block_re ]]; then
    block=${BASH_REMATCH[1]}
    if [[ $block == "$name" ]]; then
      [[ $found == false ]] || fail "$lock_name:$line_no: [$name] appears twice"
      found=true
    fi
    continue
  fi
  [[ $line =~ $key_re ]] || fail "$lock_name:$line_no: want [name] or key = value, got: $line"
  key=${BASH_REMATCH[1]}
  value=${BASH_REMATCH[2]}
  [[ -n $block ]] || fail "$lock_name:$line_no: $line is outside an entry"
  [[ $block == "$name" ]] || continue
  case $key in
  version | url | archive | binary) set_key "$key" "$value" ;;
  os.darwin | os.linux)
    if [[ $key == "os.$os" ]]; then
      set_key os_name "$value"
    fi
    ;;
  arch.amd64 | arch.arm64)
    if [[ $key == "arch.$arch" ]]; then
      set_key arch_name "$value"
    fi
    ;;
  sha256.darwin/arm64 | sha256.darwin/amd64 | sha256.linux/amd64 | sha256.linux/arm64)
    key_platform=${key#sha256.}
    set_key "sha_${key_platform/\//_}" "$value"
    ;;
  *) fail "$lock_name:$line_no: unknown key $key in [$name]" ;;
  esac
done <"$lock"

[[ $found == true ]] || fail "$lock_name has no [$name] entry"
for key in version url archive binary; do
  [[ -n ${!key} ]] || fail "[$name] has no $key"
done
sha_re='^[0-9a-f]{64}$'
for each in darwin/arm64 darwin/amd64 linux/amd64 linux/arm64; do
  var=sha_${each/\//_}
  [[ -n ${!var} ]] || fail "[$name] has no sha256.$each; every entry needs one for" \
    "darwin/arm64, darwin/amd64, linux/amd64 and linux/arm64"
  [[ ${!var} =~ $sha_re ]] || fail "[$name] sha256.$each ${!var} is not 64 lowercase hex digits"
done
[[ $archive == tar.gz ]] || fail "[$name] archive $archive is not supported; want tar.gz"
want_var=sha_${os}_${arch}
want=${!want_var}

os_name=${os_name:-$os}
arch_name=${arch_name:-$arch}
url=${url//\{version\}/$version}
url=${url//\{os\}/$os_name}
url=${url//\{arch\}/$arch_name}
binary=${binary//\{version\}/$version}
binary=${binary//\{os\}/$os_name}
binary=${binary//\{arch\}/$arch_name}
[[ $url != *[{}]* ]] || fail "[$name] url $url has an unknown placeholder"
[[ $binary != *[{}]* ]] || fail "[$name] binary $binary has an unknown placeholder"
[[ $url == https://* ]] || fail "[$name] url $url is not an https URL"
installed=$root/bin/$name
[[ ! -e $installed || -f $installed ]] ||
  fail "bin/$name exists and is not a regular file; move it away and run fetch-tool.sh again"

tmp=$(mktemp -d "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/fetch-tool.XXXXXX") ||
  fail "creating a temporary directory failed"
download=$tmp/download
echo "fetch-tool: downloading $name $version for $platform from $url" >&2
curl --disable --fail --silent --show-error --location --proto '=https' --proto-redir '=https' \
  --retry 3 --connect-timeout 30 --max-time 600 --output "$download" "$url" ||
  fail "downloading $url failed"

if command -v sha256sum >/dev/null 2>&1; then
  got=$(sha256sum "$download") || fail "hashing the download failed"
else
  got=$(shasum -a 256 "$download") || fail "hashing the download failed"
fi
got=${got%% *}
[[ $got == "$want" ]] ||
  fail "sha256 mismatch for $url: got $got, want $want ($lock_name); nothing was installed"

mkdir "$tmp/unpacked" || fail "creating $tmp/unpacked failed"
tar -xzf "$download" -C "$tmp/unpacked" "$binary" || fail "extracting $binary from $url failed"
[[ -f $tmp/unpacked/$binary ]] || fail "extracting $binary from $url failed: not a regular file"
mkdir -p "$root/bin" || fail "creating bin/ failed"
# Installed by a rename in bin/, so a reader never sees a half-written binary.
staged=$root/bin/.$name.$$
if ! cp "$tmp/unpacked/$binary" "$staged" || ! chmod 0755 "$staged" ||
  ! mv -f "$staged" "$installed"; then
  fail "installing bin/$name failed; bin/.$name.$$ may be left over"
fi
echo "fetch-tool: installed $name $version for $platform as bin/$name" >&2
printf '%s\n' "$installed"
