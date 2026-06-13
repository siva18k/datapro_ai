"""Lightweight MCP server for free email via SMTP/IMAP (Gmail app password, etc.)."""

from __future__ import annotations

import email
import imaplib
import json
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from mcp.server.fastmcp import FastMCP

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

if load_dotenv is not None:
    project_env = Path(__file__).resolve().parent / ".env"
    load_dotenv(project_env, override=False)
    load_dotenv(override=False)

MCP_HOST = os.environ.get("EMAIL_MCP_HOST", os.environ.get("MCP_HOST", "0.0.0.0"))
MCP_PORT = int(os.environ.get("EMAIL_MCP_PORT", "8010"))
MCP_PATH = os.environ.get("EMAIL_MCP_PATH", "/mcp")
MCP_TRANSPORT = os.environ.get("EMAIL_MCP_TRANSPORT", "streamable-http")

SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_FROM = os.environ.get("SMTP_FROM", SMTP_USER)
SMTP_USE_TLS = os.environ.get("SMTP_USE_TLS", "true").lower() in ("1", "true", "yes")

IMAP_HOST = os.environ.get("IMAP_HOST", "imap.gmail.com")
IMAP_PORT = int(os.environ.get("IMAP_PORT", "993"))
IMAP_USER = os.environ.get("IMAP_USER", SMTP_USER)
IMAP_PASSWORD = os.environ.get("IMAP_PASSWORD", SMTP_PASSWORD)

ALLOWLIST = {
    addr.strip().lower()
    for addr in os.environ.get("EMAIL_TO_ALLOWLIST", "").split(",")
    if addr.strip()
}

mcp = FastMCP(
    "email-smtp",
    instructions=(
        "Send and read email through configured SMTP/IMAP credentials. "
        "Use send_email for outbound mail and search_inbox to list recent messages."
    ),
    host=MCP_HOST,
    port=MCP_PORT,
    streamable_http_path=MCP_PATH,
    stateless_http=True,
)


def _smtp_configured() -> bool:
    return bool(SMTP_HOST and SMTP_USER and SMTP_PASSWORD and SMTP_FROM)


def _imap_configured() -> bool:
    return bool(IMAP_HOST and IMAP_USER and IMAP_PASSWORD)


def _check_recipient(to: str) -> None:
    if not ALLOWLIST:
        return
    recipients = [part.strip().lower() for part in to.replace(";", ",").split(",") if part.strip()]
    blocked = [r for r in recipients if r not in ALLOWLIST]
    if blocked:
        raise ValueError(
            f"Recipient(s) not in EMAIL_TO_ALLOWLIST: {', '.join(blocked)}. "
            "Set EMAIL_TO_ALLOWLIST in .env or leave empty for no restriction."
        )


def _connect_smtp() -> smtplib.SMTP:
    if not _smtp_configured():
        raise RuntimeError(
            "SMTP not configured. Set SMTP_HOST, SMTP_USER, SMTP_PASSWORD, and SMTP_FROM in .env."
        )
    server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30)
    if SMTP_USE_TLS:
        server.starttls()
    server.login(SMTP_USER, SMTP_PASSWORD)
    return server


def _connect_imap() -> imaplib.IMAP4_SSL:
    if not _imap_configured():
        raise RuntimeError(
            "IMAP not configured. Set IMAP_HOST, IMAP_USER, and IMAP_PASSWORD in .env."
        )
    client = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    client.login(IMAP_USER, IMAP_PASSWORD)
    return client


@mcp.tool()
def send_email(to: str, subject: str, body: str, html: bool = False) -> str:
    """Send an email message via SMTP."""
    to = to.strip()
    subject = subject.strip()
    if not to or not subject:
        raise ValueError("to and subject are required")
    _check_recipient(to)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM
    msg["To"] = to
    subtype = "html" if html else "plain"
    msg.attach(MIMEText(body, subtype, "utf-8"))

    with _connect_smtp() as server:
        server.sendmail(SMTP_FROM, [to], msg.as_string())

    return json.dumps({"ok": True, "to": to, "subject": subject, "from": SMTP_FROM})


@mcp.tool()
def search_inbox(query: str = "", limit: int = 10) -> str:
    """List recent inbox messages (subject, from, date). Optional IMAP TEXT search."""
    limit = max(1, min(limit, 50))
    client = _connect_imap()
    try:
        client.select("INBOX")
        criterion = f'(TEXT "{query}")' if query.strip() else "ALL"
        status, data = client.search(None, criterion)
        if status != "OK":
            raise RuntimeError(f"IMAP search failed: {status}")
        ids = data[0].split()
        ids = ids[-limit:]
        ids.reverse()
        messages: list[dict] = []
        for msg_id in ids:
            status, fetched = client.fetch(msg_id, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
            if status != "OK" or not fetched:
                continue
            raw = fetched[0][1] if isinstance(fetched[0], tuple) else b""
            parsed = email.message_from_bytes(raw)
            messages.append(
                {
                    "id": msg_id.decode(),
                    "from": parsed.get("From", ""),
                    "subject": parsed.get("Subject", ""),
                    "date": parsed.get("Date", ""),
                }
            )
        return json.dumps(messages, indent=2)
    finally:
        try:
            client.logout()
        except Exception:
            pass


@mcp.tool()
def mailbox_status() -> str:
    """Return SMTP/IMAP configuration status (no secrets)."""
    return json.dumps(
        {
            "smtp_configured": _smtp_configured(),
            "imap_configured": _imap_configured(),
            "smtp_host": SMTP_HOST,
            "smtp_from": SMTP_FROM or None,
            "allowlist_enabled": bool(ALLOWLIST),
            "allowlist_count": len(ALLOWLIST),
        },
        indent=2,
    )


def main() -> None:
    if MCP_TRANSPORT == "stdio":
        mcp.run(transport="stdio")
    else:
        mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
