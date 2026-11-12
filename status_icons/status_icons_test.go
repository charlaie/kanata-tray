package status_icons

import (
	"bytes"
	"image"
	"os"
	"path/filepath"
	"testing"
)

func preserveStatusIcons(t *testing.T) {
	t.Helper()
	d, c, p, r := Default, Crash, Pause, LiveReload
	t.Cleanup(func() { Default, Crash, Pause, LiveReload = d, c, p, r })
}

func TestIsTemplateFilename(t *testing.T) {
	cases := map[string]bool{
		"mouseTemplate.png":           true,
		"mousetemplate.png":           false, // must be case-sensitive to match.
		"/abs/path/mouseTemplate.ico": true,
		"defaultTemplate":             true,
		"mouse.png":                   false,
		"template_mouse.png":          false,
		"mouseTemplate.png.disabled":  false,
		"live-reloadTemplate.jpg":     true,
	}
	for path, want := range cases {
		if got := IsTemplateFilename(path); got != want {
			t.Errorf("IsTemplateFilename(%q) = %v, want %v", path, got, want)
		}
	}
}

func TestLoadCustomStatusIcons(t *testing.T) {
	preserveStatusIcons(t)
	configDir := t.TempDir()
	iconsDir := filepath.Join(configDir, statusIconsDir)
	if err := os.MkdirAll(iconsDir, 0o755); err != nil {
		t.Fatal(err)
	}

	files := map[string]string{
		"default.ico":         "plain default",
		"defaultTemplate.png": "template default",
		"pause.custom.ico":    "plain pause",
		"crash.ico":           "",
	}
	for name, content := range files {
		if err := os.WriteFile(filepath.Join(iconsDir, name), []byte(content), 0o644); err != nil {
			t.Fatal(err)
		}
	}

	crashBefore := Crash
	if err := LoadCustomStatusIcons(configDir); err != nil {
		t.Fatalf("LoadCustomStatusIcons: %v", err)
	}

	// A `<status>Template.*` file wins over a plain `<status>.*` one.
	if got := string(Default.Data); got != "template default" {
		t.Errorf("Default.Data = %q, want the template file's content", got)
	}
	if !Default.IsTemplate {
		t.Error("Default.IsTemplate = false, want true")
	}

	if got := string(Pause.Data); got != "plain pause" {
		t.Errorf("Pause.Data = %q, want the plain file's content", got)
	}
	if Pause.IsTemplate {
		t.Error("Pause.IsTemplate = true, want false")
	}

	// An empty file is ignored instead of being passed to systray, where it
	// would panic on `&iconBytes[0]`.
	if string(Crash.Data) != string(crashBefore.Data) {
		t.Error("Crash was overwritten by an empty icon file")
	}

	// Not overridden, keeps the embedded icon.
	if len(LiveReload.Data) == 0 || !LiveReload.IsTemplate {
		t.Errorf("LiveReload = %d bytes, template=%v; want embedded template icon",
			len(LiveReload.Data), LiveReload.IsTemplate)
	}
}

func TestPreviouslyBundledIconIsRespectedAsOverride(t *testing.T) {
	preserveStatusIcons(t)
	legacy, err := os.ReadFile("testdata/legacy-default.ico")
	if err != nil {
		t.Fatal(err)
	}
	dir := t.TempDir()
	icons := filepath.Join(dir, statusIconsDir)
	if err := os.Mkdir(icons, 0o755); err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(icons, "default.ico")
	if err := os.WriteFile(path, legacy, 0o644); err != nil {
		t.Fatal(err)
	}
	if err := LoadCustomStatusIcons(dir); err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(Default.Data, legacy) || Default.IsTemplate {
		t.Fatal("previously bundled icon was not loaded as a plain override")
	}
	if content, err := os.ReadFile(path); err != nil || !bytes.Equal(content, legacy) {
		t.Fatal("override file was modified")
	}
}

func TestExportedDefaultsKeepTemplateRendering(t *testing.T) {
	preserveStatusIcons(t)
	dir := t.TempDir()
	if err := CreateDefaultStatusIconsDirIfNotExists(dir); err != nil {
		t.Fatal(err)
	}
	if err := LoadCustomStatusIcons(dir); err != nil {
		t.Fatal(err)
	}
	for name, icon := range map[string]Icon{"default": Default, "pause": Pause, "crash": Crash, "live-reload": LiveReload} {
		if !icon.IsTemplate {
			t.Errorf("%s lost template rendering after export", name)
		}
		if _, err := os.Stat(filepath.Join(dir, statusIconsDir, name+"Template.ico")); err != nil {
			t.Error(err)
		}
	}
}

func TestBundledIconsAreWhiteWithTransparentBackgrounds(t *testing.T) {
	for name, data := range map[string][]byte{"default": defaultIconData, "pause": pauseIconData, "crash": crashIconData, "live-reload": liveReloadIconData} {
		img, _, err := image.Decode(bytes.NewReader(data))
		if err != nil {
			t.Fatal(err)
		}
		visible, transparent := false, false
		for y := img.Bounds().Min.Y; y < img.Bounds().Max.Y; y++ {
			for x := img.Bounds().Min.X; x < img.Bounds().Max.X; x++ {
				r, g, b, a := img.At(x, y).RGBA()
				if a == 0 {
					transparent = true
					continue
				}
				visible = true
				if r != a || g != a || b != a {
					t.Fatalf("%s contains non-white artwork", name)
				}
			}
		}
		if !visible || !transparent {
			t.Errorf("%s needs visible artwork and transparency", name)
		}
	}
}

func TestLoadCustomStatusIconsMissingDir(t *testing.T) {
	if err := LoadCustomStatusIcons(t.TempDir()); err != nil {
		t.Errorf("LoadCustomStatusIcons on a config dir without status_icons: %v", err)
	}
}
