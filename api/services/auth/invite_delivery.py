from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage


def send_invite_email(
    *,
    recipient: str,
    invite_link: str,
    inviter_email: str,
    workspace_label: str = "Maia",
) -> tuple[bool, str | None]:
    """Send an invitation email via SMTP if configured.

    Returns:
      (sent, error_message)
    """
    host = str(os.getenv("MAIA_SMTP_HOST", "")).strip()
    if not host:
        return False, "SMTP not configured (MAIA_SMTP_HOST missing)."

    port = int(os.getenv("MAIA_SMTP_PORT", "587"))
    user = str(os.getenv("MAIA_SMTP_USER", "")).strip()
    password = str(os.getenv("MAIA_SMTP_PASSWORD", "")).strip()
    from_addr = str(os.getenv("MAIA_SMTP_FROM", "maia@localhost")).strip()
    use_tls = str(os.getenv("MAIA_SMTP_USE_TLS", "true")).strip().lower() not in {"0", "false", "no"}

    msg = EmailMessage()
    msg["From"] = from_addr
    msg["To"] = recipient
    msg["Subject"] = f"You are invited to {workspace_label}"
    msg.set_content(
        "\n".join(
            [
                f"{inviter_email} invited you to join {workspace_label}.",
                "",
                "Open this secure invite link to set your password and access the platform:",
                invite_link,
                "",
                "If you were not expecting this invitation, you can ignore this email.",
            ]
        )
    )

    try:
        smtp_cls = smtplib.SMTP_SSL if (use_tls and port == 465) else smtplib.SMTP
        with smtp_cls(host, port, timeout=15) as server:
            if use_tls and port != 465:
                server.starttls()
            if user and password:
                server.login(user, password)
            server.sendmail(from_addr, [recipient], msg.as_string())
        return True, None
    except Exception as exc:  # pragma: no cover - network/SMTP dependent
        return False, str(exc)
