{ pkgs }: {
  deps = [
    pkgs.python311
    pkgs.playwright-driver
    pkgs.glib
    pkgs.nss
    pkgs.nspr
    pkgs.atk
    pkgs.at-spi2-atk
    pkgs.libdrm
    pkgs.mesa
    pkgs.gtk3
  ];
}
