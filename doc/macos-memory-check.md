# macOS tray icon memory leak

## What was wrong

kanata-tray used to depend on `github.com/getlantern/systray` v1.2.2. Its macOS
`setIcon` looked like this:

```objc
void setIcon(const char* iconBytes, int length, bool template) {
  NSData* buffer = [NSData dataWithBytes: iconBytes length:length];
  NSImage *image = [[NSImage alloc] initWithData:buffer];
  ...
  runInMainThread(@selector(setIcon:), (id)image);
}
```

Go calls this function on a cgo thread, and that thread has no autorelease pool.
Decoding an `NSImage` creates autoreleased objects, and with no pool to clean them up
they were never freed. Each icon change leaked a little memory. kanata-tray changes
the icon on every layer change, every config reload (twice) and every pause, so a
long-running tray kept growing.

The leaked memory belongs to the Objective-C runtime, not Go, so it doesn't show up in
Go heap profiles or `pprof`. You have to look at the whole process, for example with
`footprint`.

## The fix

1. **Switched to `fyne.io/systray`.** It's a maintained fork of the same library, and
   its `setIcon` wraps the decode in `@autoreleasepool { ... }`, so the temporary objects
   are freed after each call. The Go API is almost the same: only the import path in
   `main.go` and `app/app.go` changed.
2. **Skip unchanged icons.** `SystrayApp.setIcon` in `app/app.go` returns early when
   the new icon has the same bytes and the same template flag as the current one. Most
   layer changes map to the same icon, so most calls never reach native code.

Switching libraries also changes Linux. fyne.io/systray talks to the desktop over D-Bus
instead of through libayatana-appindicator and GTK, so the Linux build no longer needs
cgo or those packages. On Linux the library decodes icons with Go's `image.Decode`,
so `status_icons/decoders.go` registers the ICO, PNG and JPEG decoders and
`status_icons/decoders_test.go` checks they stay registered.

## Checking for a regression

`scripts/check-macos-tray-memory.py` runs a real tray build against a fake kanata
that sends thousands of layer-change and reload messages over TCP. It doesn't touch
your keyboard or your normal config. Run it while logged in to the desktop:

```sh
go build -trimpath -o dist/kanata-tray-macos .
python3 scripts/check-macos-tray-memory.py dist/kanata-tray-macos
```

A temporary icon appears in the menu bar for a minute or so. The script checks that:

- sending the same icon over and over doesn't cause any native updates;
- switching between two different icons updates every time;
- the same image with a different template flag still updates;
- each config reload makes the icon blink (two updates).

After each phase it records the process's `phys_footprint`. It fails if memory grows
by more than 10 MB from the first switching phase to the template phase (10,000 updates
apart). The script prints the folder it saved logs and `results.json` to.

On an M1 Pro, the fixed build stayed at about 21 MB through 6,000 same-icon events,
10,000 icon switches, 5,000 template-flag switches and 10 reloads.

The script only checks memory and update counts. It doesn't check how the icon looks,
and it doesn't test Linux or Windows.
