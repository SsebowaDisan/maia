# Gmail DWD Environment Setup (No User OAuth)

Use this for server-side report delivery with Google Workspace Domain-Wide Delegation (DWD).

## Required Environment Variables

Set these variables at runtime:

```bash
MAIA_GMAIL_SA_JSON_B64=<base64_of_service_account_json>
MAIA_GMAIL_IMPERSONATE=disan@micrurus.com
MAIA_GMAIL_FROM=disan@micrurus.com
```

Fallback option (if base64 is not used):

```bash
MAIA_GMAIL_SA_JSON_PATH=/absolute/path/to/service_account.json
```

Priority:
- `MAIA_GMAIL_SA_JSON_B64` (preferred)
- `MAIA_GMAIL_SA_JSON_PATH` (fallback)

## Generate `MAIA_GMAIL_SA_JSON_B64`

Do this locally and paste only the encoded value into your secret store.

macOS/Linux:

```bash
base64 -w 0 path/to/service_account.json
```

Windows PowerShell:

```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes("path\\to\\service_account.json"))
```

## Security Rules

- Never commit raw service-account JSON to git.
- Never paste private keys into tracked files.
- Use secret managers or deployment environment variables in production.
- Rotate service-account keys regularly and immediately after accidental exposure.

## Smoke Test

From repo root:

```bash
python scripts/send_test_email.py
```

Expected output:

```text
Message sent. id=<gmail_message_id>
```
