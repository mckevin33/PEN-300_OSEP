# OSEP Loader Toolkit

Shellcode loader toolkit for OSEP exam preparation. One directory per payload format — each ships with its own `README.md` and a short example.

- [loader/](loader/) — C# meterpreter shellcode loader (D/Invoke + AES-256-CBC + AMSI/ETW bypass + RW->RX)
- [vba/](vba/) — VBA macro loader for `.docm`
- [powershell/](powershell/) — PowerShell in-memory loader (reflective P/Invoke)
- [installutil/](installutil/) — Loader executed via `InstallUtil.exe /U` (AppLocker/AMSI/CLM bypass)
- [hta/](hta/) — Phishing `.hta` generator (PowerShell Reflection.Load or InstallUtil chain)
- [lnk/](lnk/) — Windows `.lnk` shortcut builder (command or in-memory .NET loader)

## Requirements

- `msfvenom` (metasploit-framework)
- `mono-complete` (mcs compiler)
- `pycryptodome` (`pip install pycryptodome`)
- `swaks` — for email delivery

## Disclaimer

Intended solely for authorized security testing and OSEP exam preparation.
