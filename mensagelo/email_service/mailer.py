import smtplib
from email.mime.text import MIMEText
from typing import List
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from . import config

class SmtpError(Exception):
    pass

def _build_message(subject: str, body: str, sender: str, recipients: List[str]) -> MIMEText:
    msg = MIMEText(body, _charset="utf-8")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    return msg

@retry(
    retry=retry_if_exception_type(SmtpError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
def send_email(recipients: List[str], subject: str, body: str) -> None:
    if not config.SMTP_SERVER:
        raise SmtpError("SMTP_SERVER no configurado")

    sender = config.SMTP_USERNAME or "noreply@example.com"
    msg = _build_message(subject, body, sender, recipients)

    try:
        if config.SMTP_USE_TLS:
            client = smtplib.SMTP(config.SMTP_SERVER, config.SMTP_PORT, timeout=config.SMTP_TIMEOUT_SECONDS)
            client.ehlo()
            client.starttls()
            client.ehlo()
        else:
            client = smtplib.SMTP_SSL(config.SMTP_SERVER, config.SMTP_PORT, timeout=config.SMTP_TIMEOUT_SECONDS)

        if config.SMTP_USERNAME:
            client.login(config.SMTP_USERNAME, config.SMTP_PASSWORD or "")

        client.sendmail(sender, recipients, msg.as_string())
        try:
            client.quit()
        except Exception:
            pass
    except (smtplib.SMTPException, OSError) as e:
        raise SmtpError(f"SMTP error: {e}") from e