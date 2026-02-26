from __future__ import annotations

from maia.integrations.gmail_dwd import GmailDwdError, send_report_email


def main() -> int:
    try:
        result = send_report_email(
            to_email="ssebowadisan1@gmail.com",
            subject="Maia DWD Test",
            body_text=(
                "This is a Maia Domain-Wide Delegation smoke test.\n\n"
                "If you received this, the server-side Gmail DWD sender is working."
            ),
            body_html=(
                "<p>This is a <strong>Maia Domain-Wide Delegation</strong> smoke test.</p>"
                "<p>If you received this, the server-side Gmail DWD sender is working.</p>"
            ),
        )
    except GmailDwdError as exc:
        code = getattr(exc, "code", "gmail_dwd_error")
        print(f"Send failed [{code}]: {exc}")
        return 1
    except Exception as exc:
        print(f"Send failed: {exc}")
        return 1

    print(f"Message sent. id={result.get('id') or ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
