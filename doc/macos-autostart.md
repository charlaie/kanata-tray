# Start kanata-tray at login on macOS

On macOS, kanata has to run as root to use the Karabiner virtual keyboard driver.
kanata-tray starts kanata as its own child process, so the tray has to run as root
too. This guide sets up a login job that does that without asking for a password.

```
LaunchAgent (runs as you, at login)
  └─ sudo -n /usr/local/libexec/kanata-tray-launch   (allowed by a sudoers rule)
       └─ /usr/local/libexec/kanata-tray              (root)
            └─ kanata                                 (root)
```

> [!WARNING]
> **This lets anything running as your user run commands as root.** The tray reads
> `kanata-tray.toml` from your home folder, and that file sets which program to start
> as kanata and which hook commands to run, all as root. Anything that can edit the
> file can therefore run code as root. Only use this setup on a Mac where you are fine
> with that. If you don't need the menu-bar icon, the
> [kanata daemon](./macos-kanata-daemon.md) doesn't have this problem.

The examples use Apple Silicon Homebrew paths. On an Intel Mac, replace
`/opt/homebrew` with `/usr/local`. Replace `YOUR_USER` with the output of `whoami`.

## Before you start

- kanata and the Karabiner driver already work when you run them by hand with `sudo`.
- You are an administrator on this Mac.
- Nothing else starts kanata. Exit any tray you started by hand. If you followed the
  setup from issue #67, see [Moving off the issue #67 setup](#moving-off-the-issue-67-setup)
  first.

## 1. Install the binary

Build it from this repository and copy it somewhere root owns. A copy owned by your
user would let you change what runs as root:

```sh
go build -trimpath -o dist/kanata-tray-macos .
sudo install -d -o root -g wheel -m 755 /usr/local/libexec
sudo install -o root -g wheel -m 755 dist/kanata-tray-macos /usr/local/libexec/kanata-tray
```

## 2. Configure a preset to start automatically

```sh
mkdir -p "$HOME/Library/Application Support/kanata-tray" "$HOME/Library/Logs/kanata-tray"
touch "$HOME/Library/Application Support/kanata-tray/kanata-tray.toml"
open -e "$HOME/Library/Application Support/kanata-tray/kanata-tray.toml"
```

Make sure at least one preset has `autorun = true`. Use absolute paths, because `~`
will refer to root's home folder:

```toml
[presets.main]
kanata_executable = '/opt/homebrew/bin/kanata'
kanata_config = '/Users/YOUR_USER/.config/kanata/kanata.kbd'
autorun = true
```

## 3. Create the launcher script

The sudoers rule in the next step allows this one script and nothing else. The script
clears the environment and points the tray at your config and log folders. Without
that, the tray would look in root's folders.

```sh
sudo tee /usr/local/libexec/kanata-tray-launch >/dev/null <<'EOF'
#!/bin/sh
exec /usr/bin/env -i \
  HOME="/Users/YOUR_USER" \
  PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin" \
  KANATA_TRAY_CONFIG_DIR="/Users/YOUR_USER/Library/Application Support/kanata-tray" \
  KANATA_TRAY_LOG_DIR="/Users/YOUR_USER/Library/Logs/kanata-tray" \
  /usr/local/libexec/kanata-tray
EOF
sudo sed -i '' "s/YOUR_USER/$(whoami)/g" /usr/local/libexec/kanata-tray-launch
sudo chown root:wheel /usr/local/libexec/kanata-tray-launch
sudo chmod 755 /usr/local/libexec/kanata-tray-launch
cat /usr/local/libexec/kanata-tray-launch
```

## 4. Allow it to run without a password

Write the rule to a temporary file and check it with `visudo`. Only install it if the
check passes, because a broken sudoers file can lock you out of `sudo`. The trailing
`""` means the script can't be given any arguments.

```sh
echo "$(whoami) ALL=(root) NOPASSWD: /usr/local/libexec/kanata-tray-launch \"\"" > /tmp/kanata-tray.sudoers
/usr/sbin/visudo -cf /tmp/kanata-tray.sudoers \
  && sudo install -o root -g wheel -m 0440 /tmp/kanata-tray.sudoers /private/etc/sudoers.d/local-kanata-tray
rm /tmp/kanata-tray.sudoers
sudo visudo -c
sudo -n -l /usr/local/libexec/kanata-tray-launch   # prints the path if the rule works
```

If `visudo -c` complains that some *other* file has bad permissions, fix that file
with `sudo chmod 0440 <file>`.

## 5. Create the login job

```sh
mkdir -p "$HOME/Library/LaunchAgents"
cat > "$HOME/Library/LaunchAgents/local.kanata-tray.plist" <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>local.kanata-tray</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/sudo</string>
        <string>-n</string>
        <string>/usr/local/libexec/kanata-tray-launch</string>
    </array>
    <key>LimitLoadToSessionType</key><string>Aqua</string>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key>
    <dict><key>SuccessfulExit</key><false/></dict>
    <key>ThrottleInterval</key><integer>20</integer>
</dict>
</plist>
EOF
plutil -lint "$HOME/Library/LaunchAgents/local.kanata-tray.plist"
```

- `LimitLoadToSessionType = Aqua`: start only in a graphical login session, not over SSH.
- `KeepAlive.SuccessfulExit = false`: if the tray exits with an error, start it again,
  waiting at least `ThrottleInterval` (20) seconds.

## 6. Start it

```sh
launchctl enable "gui/$(id -u)/local.kanata-tray"
launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/local.kanata-tray.plist"
launchctl print "gui/$(id -u)/local.kanata-tray" | grep -E 'state|last exit'
```

You should see `state = running` and the icon in the menu bar. Test a remapped key,
then log out and back in to make sure it starts on its own.

## Day to day

> [!NOTE]
> **Exit tray** exits with status 1, so launchd counts it as a failure and starts the
> tray again about 20 seconds later. To stop the tray for real, use `bootout` below.

| Task | Command |
| --- | --- |
| Restart | `launchctl kickstart -k "gui/$(id -u)/local.kanata-tray"` |
| Stop, and don't start at login | `launchctl bootout "gui/$(id -u)/local.kanata-tray"` then `launchctl disable "gui/$(id -u)/local.kanata-tray"` |
| Turn back on | Run step 6 again |

To install a newer build, rebuild, copy it over the old binary, and restart:

```sh
go build -trimpath -o dist/kanata-tray-macos .
sudo install -o root -g wheel -m 755 dist/kanata-tray-macos /usr/local/libexec/kanata-tray
launchctl kickstart -k "gui/$(id -u)/local.kanata-tray"
```

## If it doesn't start

```sh
launchctl print "gui/$(id -u)/local.kanata-tray" | grep -E 'state|last exit'
sudo -n -l /usr/local/libexec/kanata-tray-launch
sudo tail -50 "$HOME/Library/Logs/kanata-tray/kanata_tray_lastrun.log"   # written by root
```

- `sudo -n -l` says a password is required: the sudoers rule isn't active. Repeat step 4.
- No log file: the tray never ran. Run `sudo /usr/local/libexec/kanata-tray-launch` in a
  terminal to see the error.
- The tray runs but kanata fails: open the preset's log from the tray menu. The cause is
  usually an Input Monitoring permission or a driver problem, not this setup.

## Moving off the issue #67 setup

The recipe in [issue #67](https://github.com/rszyma/kanata-tray/issues/67) used a job
called `com.kanata-tray-macos` and a sudoers rule at
`/private/etc/sudoers.d/kanata-tray-macos`. Only one of the two jobs should run.

### Using the script

`scripts/migrate-macos-autostart.sh` does steps 1 and 3 to 6 above for you. It uses
your existing `kanata-tray.toml`, so skip step 2. It also stops the old job, and puts
the old setup back if the new tray fails to start kanata. Build first, then do a dry
run to check the files it would install:

```sh
go build -trimpath -o dist/kanata-tray-macos .
bash scripts/migrate-macos-autostart.sh --dry-run
bash scripts/migrate-macos-autostart.sh
```

The script stops without changing anything if any of these exist: the new LaunchAgent,
the installed binary, the launcher, the sudoers rule, or a `local.kanata` daemon.
Backups are saved to `~/Library/Application Support/kanata-tray/backups/`. It leaves
the old sudoers rule in place and prints the command to remove it once you're happy.

### By hand

Stop and disable the old job. Remapping stops at this point:

```sh
launchctl bootout "gui/$(id -u)/com.kanata-tray-macos"   # "not found" means it was already stopped
launchctl disable "gui/$(id -u)/com.kanata-tray-macos"
mv ~/Library/LaunchAgents/com.kanata-tray-macos.plist ~/Library/LaunchAgents/com.kanata-tray-macos.plist.disabled
```

Then follow steps 1 to 6. Once the new setup has survived a logout and login, retire
the old sudoers rule:

```sh
sudo mv /private/etc/sudoers.d/kanata-tray-macos /private/etc/kanata-tray-macos.sudoers.disabled
sudo visudo -c
```
