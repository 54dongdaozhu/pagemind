import logging
import smtplib
from concurrent.futures import ThreadPoolExecutor
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.config import (
    APP_BASE_URL,
    SMTP_FROM,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_USE_TLS,
    SMTP_USER,
)

logger = logging.getLogger(__name__)
_executor = ThreadPoolExecutor(max_workers=1)


def _send_sync(to: str, subject: str, body_html: str) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM or SMTP_USER
    msg["To"] = to
    msg.attach(MIMEText(body_html, "html", "utf-8"))
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
            if SMTP_USE_TLS:
                server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_FROM or SMTP_USER, to, msg.as_string())
    except Exception as exc:
        logger.error("邮件发送失败 to=%s: %s", to, exc)


def send_email(to: str, subject: str, body_html: str) -> None:
    if not SMTP_HOST or not SMTP_USER:
        logger.warning("SMTP 未配置，跳过发送邮件至 %s\n正文:\n%s", to, body_html)
        return
    _executor.submit(_send_sync, to, subject, body_html)


def send_verification_email(to: str, token: str) -> None:
    url = f"{APP_BASE_URL}/api/auth/verify-email?token={token}"
    send_email(
        to,
        "验证您的邮箱",
        f"<p>点击以下链接验证您的邮箱（24小时内有效）：</p><p><a href=\"{url}\">{url}</a></p>",
    )


def send_password_reset_email(to: str, token: str) -> None:
    url = f"{APP_BASE_URL}/api/auth/reset-password?token={token}"
    send_email(
        to,
        "重置您的密码",
        f"<p>点击以下链接重置密码（1小时内有效）：</p><p><a href=\"{url}\">{url}</a></p>",
    )


def send_change_email_verification(to: str, token: str) -> None:
    url = f"{APP_BASE_URL}/api/auth/verify-email-change?token={token}"
    send_email(
        to,
        "确认您的新邮箱",
        f"<p>点击以下链接确认新邮箱（24小时内有效）：</p><p><a href=\"{url}\">{url}</a></p>",
    )
