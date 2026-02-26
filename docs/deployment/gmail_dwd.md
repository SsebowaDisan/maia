# Gmail DWD (Service Account) for Company Agent Report Sending

Use this setup to send company-agent reports from a fixed Workspace user without interactive OAuth.

Sender/impersonated mailbox:
- `disan@micrurus.com`

Required OAuth scope:
- `https://www.googleapis.com/auth/gmail.send`

## 1) Google Cloud Setup

1. Create/select a Google Cloud project.
2. Enable **Gmail API** for that project.
3. Create a **Service Account**.
4. In Service Account settings, enable **Domain-wide delegation**.
5. Download the service account JSON key (do not commit it to git).
6. Copy the service account **Client ID** (used in Admin Console delegation).

## 2) Google Admin Console Setup

1. Open **Security -> API controls -> Manage Domain-wide Delegation**.
2. Add a new API client:
   - Client ID: service account client ID from Google Cloud
   - OAuth scopes: `https://www.googleapis.com/auth/gmail.send`
3. Save changes.

## 3) Runtime Environment Variables

Set one credential source:

1. `MAIA_GMAIL_SA_JSON_B64`
: Base64-encoded service-account JSON (useful for containers/secrets managers).

2. `MAIA_GMAIL_SA_JSON_PATH`
: Absolute path to the service-account JSON file.

Set sender/impersonation:

1. `MAIA_GMAIL_IMPERSONATE=disan@micrurus.com`
2. `MAIA_GMAIL_FROM=disan@micrurus.com`

Example:

```bash
MAIA_GMAIL_SA_JSON_PATH=/secure/secrets/maia-gmail-sa.json
MAIA_GMAIL_IMPERSONATE=disan@micrurus.com
MAIA_GMAIL_FROM=disan@micrurus.com
```

For secure base64 generation examples, see:
- `docs/deployment/gmail_dwd_env.md`

## 4) Behavior in Company Agent

- Report email sending is performed server-side through the Mailer Service.
- No interactive Gmail OAuth is required for this delivery path.
- Sending uses Gmail API `users.messages.send` with DWD impersonation.

## 5) Common Failures and Fixes

1. Gmail API not enabled
: Enable Gmail API in the service account's Google Cloud project.

2. Delegation denied / unauthorized client
: Confirm domain-wide delegation entry in Admin Console with the exact scope above.

3. Mailbox unavailable
: Verify the impersonated mailbox exists and is active (not suspended).

## 6) Smoke Test

Run:

```bash
python scripts/send_test_email.py
```

Expected output:

```text
Message sent. id=<gmail_message_id>
```
