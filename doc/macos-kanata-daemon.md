# Start kanata at boot on macOS (without the tray)

If you don't need the menu-bar icon, you can have launchd run kanata as root directly.
This avoids the passwordless-sudo rule the [tray setup](./macos-autostart.md) needs.

Things to know first:

- It's a system-wide job with a single kanata config. It doesn't switch configs per user.
- It starts at boot, before anyone logs in, so your remapping also applies at the login
  and lock screens.
- It can't run alongside kanata-tray, and the tray can't connect to it. If you set up
  the tray at login, stop it first:

  ```sh
  launchctl bootout "gui/$(id -u)/local.kanata-tray"
  launchctl disable "gui/$(id -u)/local.kanata-tray"
  ```

  If you used the setup from issue #67, follow the "By hand" part of
  [Moving off the issue #67 setup](./macos-autostart.md#moving-off-the-issue-67-setup)
  instead.

The examples use Apple Silicon Homebrew paths. On an Intel Mac, replace
`/opt/homebrew` with `/usr/local`.

## 1. Check the config

```sh
/opt/homebrew/bin/kanata --check --cfg "$HOME/.config/kanata/kanata.kbd"
```

## 2. Create the daemon

launchd doesn't expand `~` or `$HOME` inside a plist, so the paths have to be absolute.
The `sed` line fills in your username:

```sh
sudo tee /Library/LaunchDaemons/local.kanata.plist >/dev/null <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>local.kanata</string>
    <key>ProgramArguments</key>
    <array>
        <string>/opt/homebrew/bin/kanata</string>
        <string>--cfg</string>
        <string>/Users/YOUR_USER/.config/kanata/kanata.kbd</string>
        <string>--no-wait</string>
        <string>--quiet</string>
    </array>
    <key>WorkingDirectory</key><string>/Users/YOUR_USER/.config/kanata</string>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key>
    <dict><key>SuccessfulExit</key><false/></dict>
    <key>ThrottleInterval</key><integer>10</integer>
    <key>StandardOutPath</key><string>/var/log/kanata.log</string>
    <key>StandardErrorPath</key><string>/var/log/kanata.log</string>
</dict>
</plist>
EOF
sudo sed -i '' "s/YOUR_USER/$(whoami)/g" /Library/LaunchDaemons/local.kanata.plist
sudo chown root:wheel /Library/LaunchDaemons/local.kanata.plist
sudo chmod 644 /Library/LaunchDaemons/local.kanata.plist
plutil -lint /Library/LaunchDaemons/local.kanata.plist
```

- `--no-wait`: when kanata hits an error, exit straight away instead of waiting for a
  keypress. Nobody can press a key for a daemon.
- `--quiet`: only log errors.
- `KeepAlive.SuccessfulExit = false`: start kanata again if it exits with an error, but
  leave it stopped if it exits cleanly.

If your kanata version rejects a flag, check `kanata --help`.

> [!NOTE]
> launchd runs this job as root, and root can read files in your home folder. Anyone
> who can edit `kanata.kbd` can change what this daemon does, for example with `cmd`
> actions if your kanata build allows them.

## 3. Start it

```sh
sudo launchctl enable system/local.kanata
sudo launchctl bootstrap system /Library/LaunchDaemons/local.kanata.plist
sudo launchctl print system/local.kanata | grep -E 'state|last exit'
```

You should see `state = running`. Test a remapped key, then reboot to make sure it
starts on its own. If it doesn't:

```sh
sudo tail -50 /var/log/kanata.log
```

If kanata worked from a terminal but fails here, macOS probably hasn't given the
daemon Input Monitoring permission. That permission belongs to the program that
starts kanata, so what you granted your terminal doesn't apply here. Look under
**System Settings → Privacy & Security → Input Monitoring**.

## Day to day

| Task | Command |
| --- | --- |
| Restart (after editing the config) | `sudo launchctl kickstart -k system/local.kanata` |
| Stop, and don't start at boot | `sudo launchctl bootout system/local.kanata` then `sudo launchctl disable system/local.kanata` |
| Turn back on | Run step 3 again |

Stop the daemon before you go back to the tray.

[kanata discussion #1537](https://github.com/jtroo/kanata/discussions/1537) has more
on running kanata under launchd and fixing driver problems.
