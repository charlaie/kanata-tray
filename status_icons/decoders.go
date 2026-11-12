package status_icons

// Fyne's Linux tray backend uses image.Decode rather than a native image
// loader. Register all image formats supported by kanata-tray.
import (
	_ "image/jpeg"
	_ "image/png"

	_ "github.com/fyne-io/image/ico"
)
