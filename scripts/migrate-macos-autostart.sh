#!/bin/bash
# Migrate an existing issue #67 LaunchAgent to this fork's installed build.
# Run as your normal login user. --dry-run validates staged files only.
set -euo pipefail

dry_run=false
case "${1:-}" in
    --dry-run) dry_run=true ;;
    '') ;;
    *) echo "Usage: bash scripts/migrate-macos-autostart.sh [--dry-run]" >&2; exit 2 ;;
esac

if [[ "$(uname -s)" != Darwin || "$(id -u)" == 0 ]]; then
    echo "Run this on macOS as your normal login user, without sudo." >&2
    exit 1
fi

repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
binary="$repo_dir/dist/kanata-tray-macos"
old_plist="$HOME/Library/LaunchAgents/com.kanata-tray-macos.plist"
new_plist="$HOME/Library/LaunchAgents/local.kanata-tray.plist"
old_job="gui/$(id -u)/com.kanata-tray-macos"
new_job="gui/$(id -u)/local.kanata-tray"
installed_binary=/usr/local/libexec/kanata-tray
installed_launcher=/usr/local/libexec/kanata-tray-launch
new_rule=/private/etc/sudoers.d/local-kanata-tray
old_rule=/private/etc/sudoers.d/kanata-tray-macos

[[ -x "$binary" ]] || { echo "Build dist/kanata-tray-macos first." >&2; exit 1; }
[[ -f "$old_plist" ]] || { echo "The issue #67 agent was not found: $old_plist" >&2; exit 1; }
for path in "$new_plist" "$installed_binary" "$installed_launcher" "$new_rule"; do
    if [[ -e "$path" || -L "$path" ]]; then
        echo "Refusing to replace an existing installation: $path" >&2
        exit 1
    fi
done
if launchctl print system/local.kanata >/dev/null 2>&1; then
    echo "Stop the direct Kanata daemon before migrating to the tray." >&2
    exit 1
fi

staging_dir="$(mktemp -d -t kanata-tray-migration)"
backup_dir=""
switching=false
installed=false
finished=false

cleanup() {
    local status=$?
    trap - EXIT
    if [[ "$finished" != true && "$installed" == true ]]; then
        echo "Migration failed; restoring the previous setup." >&2
        launchctl bootout "$new_job" >/dev/null 2>&1 || true
        rm -f "$new_plist"
        sudo rm -f "$new_rule" "$installed_launcher" "$installed_binary" || true
        if [[ "$switching" == true ]]; then
            cp -p "$backup_dir/com.kanata-tray-macos.plist" "$old_plist"
            launchctl enable "$old_job"
            launchctl bootstrap "gui/$(id -u)" "$old_plist" || true
        fi
    fi
    rm -rf "$staging_dir"
    exit "$status"
}
trap cleanup EXIT

python3 - "$staging_dir" "$HOME" "$(id -un)" <<'PY'
import pathlib, plistlib, shlex, sys
stage, home, user = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), sys.argv[3]
environment = {
    'HOME': str(home),
    'PATH': '/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin',
    'KANATA_TRAY_CONFIG_DIR': str(home / 'Library/Application Support/kanata-tray'),
    'KANATA_TRAY_LOG_DIR': str(home / 'Library/Logs/kanata-tray'),
}
launcher = '#!/bin/sh\nexec /usr/bin/env -i ' + ' '.join(
    shlex.quote(key + '=' + value) for key, value in environment.items()
) + ' /usr/local/libexec/kanata-tray\n'
(stage / 'launcher').write_text(launcher)
(stage / 'sudoers').write_text(user + ' ALL=(root) NOPASSWD: /usr/local/libexec/kanata-tray-launch ""\n')
with (stage / 'agent.plist').open('wb') as output:
    plistlib.dump({
        'Label': 'local.kanata-tray',
        'ProgramArguments': ['/usr/bin/sudo', '-n', '/usr/local/libexec/kanata-tray-launch'],
        'LimitLoadToSessionType': 'Aqua',
        'RunAtLoad': True,
        'KeepAlive': {'SuccessfulExit': False},
        'ThrottleInterval': 20,
    }, output)
PY

/bin/sh -n "$staging_dir/launcher"
plutil -lint "$staging_dir/agent.plist"
/usr/sbin/visudo -cf "$staging_dir/sudoers"

echo "Install build: $binary"
echo "Replace job: $old_job -> $new_job"
echo "Keep configuration: $HOME/Library/Application Support/kanata-tray/kanata-tray.toml"
if [[ "$dry_run" == true ]]; then
    echo "Dry run passed. No startup settings were changed."
    finished=true
    exit 0
fi

sudo -v
backup_dir="$HOME/Library/Application Support/kanata-tray/backups/autostart-$(date +%Y%m%d-%H%M%S)"
mkdir -m 700 -p "$backup_dir" "$HOME/Library/Logs/kanata-tray"
cp -p "$old_plist" "$backup_dir/com.kanata-tray-macos.plist"
if [[ -f "$old_rule" ]]; then
    sudo cp -p "$old_rule" "$backup_dir/kanata-tray-macos.sudoers"
fi

# Stage the privileged files while the working remapper is still running.
installed=true
sudo install -d -o root -g wheel -m 755 /usr/local/libexec
sudo install -o root -g wheel -m 755 "$binary" "$installed_binary"
sudo install -o root -g wheel -m 755 "$staging_dir/launcher" "$installed_launcher"
sudo install -o root -g wheel -m 440 "$staging_dir/sudoers" "$new_rule"
sudo /usr/sbin/visudo -c
cp "$staging_dir/agent.plist" "$new_plist"
chmod 644 "$new_plist"

# This is the brief interruption to keyboard remapping.
launchctl disable "$old_job"
switching=true
if launchctl print "$old_job" >/dev/null 2>&1; then
    launchctl bootout "$old_job"
fi
mv "$old_plist" "$backup_dir/com.kanata-tray-macos.plist.disabled"

# Do not start a second remapper if an old tray is still shutting down.
for attempt in {1..30}; do
    if ! pgrep -x kanata-tray >/dev/null && ! pgrep -x kanata >/dev/null; then break; fi
    sleep 0.5
done
if pgrep -x kanata-tray >/dev/null || pgrep -x kanata >/dev/null; then
    echo "A Kanata process is still running; refusing to start a duplicate." >&2
    exit 1
fi

launchctl enable "$new_job"
launchctl bootstrap "gui/$(id -u)" "$new_plist"
for attempt in {1..30}; do
    supervisor_pid="$(launchctl print "$new_job" | awk '/^[[:space:]]*pid = / {print $3; exit}')"
    tray_pid=""
    if [[ -n "$supervisor_pid" ]]; then
        tray_pid="$(pgrep -P "$supervisor_pid" -x kanata-tray || true)"
    fi
    if [[ -n "$tray_pid" ]] && pgrep -P "$tray_pid" -x kanata >/dev/null; then
        # Kanata normally delays opening devices at startup. Do not call a
        # short-lived child that exits on a permission error a successful start.
        sleep 3
        if pgrep -P "$supervisor_pid" -x kanata-tray >/dev/null && \
           pgrep -P "$tray_pid" -x kanata >/dev/null; then
            finished=true
            break
        fi
    fi
    sleep 0.5
done
if [[ "$finished" != true ]]; then
    echo "The new tray did not start a Kanata child; inspect Library/Logs/kanata-tray." >&2
    exit 1
fi

echo "Migration complete. Test your remapped keys and tray menu now."
echo "Backup: $backup_dir"
echo "The old job is disabled and its plist has been moved out of LaunchAgents."
echo "After checking remapping and a logout/login, disable the obsolete sudo rule with:"
printf '  sudo mv %q %q\n' "$old_rule" "$backup_dir/kanata-tray-macos.sudoers.disabled"
echo "The new setup uses /private/etc/sudoers.d/local-kanata-tray instead."
