package status_icons

import (
	"bytes"
	"image"
	"os"
	"testing"
)

func TestTrayImageDecoders(t *testing.T) {
	// The Linux backend calls image.Decode, including for the embedded ICOs.
	// Exercise that decoder registry so dependency changes cannot leave icons blank.
	for name, icon := range map[string]Icon{
		"default":     Default,
		"pause":       Pause,
		"crash":       Crash,
		"live-reload": LiveReload,
	} {
		t.Run(name, func(t *testing.T) {
			img, format, err := image.Decode(bytes.NewReader(icon.Data))
			if err != nil {
				t.Fatal(err)
			}
			if format != "ico" || img.Bounds().Empty() {
				t.Fatalf("decoded %q, bounds %v; want a nonempty ICO", format, img.Bounds())
			}
		})
	}

	// Use fixtures rather than importing encoders: those imports would register
	// decoders themselves and conceal a missing production registration.
	for format, path := range map[string]string{"png": "128x128.png", "jpeg": "testdata/icon.jpg"} {
		t.Run(format, func(t *testing.T) {
			encoded, err := os.ReadFile(path)
			if err != nil {
				t.Fatal(err)
			}
			decoded, gotFormat, err := image.Decode(bytes.NewReader(encoded))
			if err != nil {
				t.Fatal(err)
			}
			if gotFormat != format || decoded.Bounds().Empty() {
				t.Fatalf("decoded %q, bounds %v; want nonempty %q", gotFormat, decoded.Bounds(), format)
			}
		})
	}
}
