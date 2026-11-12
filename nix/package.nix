{
  lib,
  buildGoModule,
  makeWrapper,
  self ? { },
  ...
}:

buildGoModule (finalAttrs: {
  pname = "kanata-tray";
  version = "git";

  src = lib.cleanSource ./..;

  vendorHash = "sha256-m+BFhpHzp8QBSoiD+mHEBryeHKhQEhO9LpXhbUTuQW4=";

  flags = [ "-trimpath" ];

  ldflags = [
    "-s"
    "-w"
    "-X main.buildVersion=${(finalAttrs.version)}"
    "-X main.buildHash=${finalAttrs.src.rev or self.shortRev or self.dirtyShortRev or "unknown"}"
    "-X main.buildDate=unknown"
  ];

  buildInputs = [
    makeWrapper
  ];

  postInstall = ''
    wrapProgram $out/bin/kanata-tray --set-default KANATA_TRAY_LOG_DIR /tmp --prefix PATH : $out/bin
  '';

  meta = with lib; {
    description = "Tray Icon for Kanata";
    longDescription = ''
      A simple wrapper for kanata to control it from tray icon.
      Works on Windows, Linux and macOS.
    '';
    homepage = "https://github.com/rszyma/kanata-tray";
    license = licenses.gpl3Plus;
    platforms = platforms.unix;
  };
})
