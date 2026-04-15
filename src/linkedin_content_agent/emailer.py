from __future__ import annotations

from email.message import EmailMessage
import smtplib

from linkedin_content_agent.config import SMTPConfig
from linkedin_content_agent.models import DeliveryResult, EmailPayload


class SMTPEmailSender:
    def __init__(self, config: SMTPConfig) -> None:
        self.config = config

    def send(self, payload: EmailPayload) -> DeliveryResult:
        if not self.config.is_configured:
            return DeliveryResult(status="skipped", detail="SMTP is not configured.")

        message = EmailMessage()
        message["Subject"] = payload.subject
        message["From"] = self.config.sender
        message["To"] = payload.recipient
        message.set_content(payload.body_text)

        try:
            if self.config.use_ssl:
                with smtplib.SMTP_SSL(self.config.host, self.config.port) as smtp:
                    self._authenticate_and_send(smtp, message)
            else:
                with smtplib.SMTP(self.config.host, self.config.port) as smtp:
                    smtp.starttls()
                    self._authenticate_and_send(smtp, message)
        except OSError as exc:
            return DeliveryResult(status="failed", detail=str(exc))

        return DeliveryResult(status="sent", detail=f"Email sent to {payload.recipient}")

    def _authenticate_and_send(self, smtp: smtplib.SMTP, message: EmailMessage) -> None:
        if self.config.username and self.config.password:
            smtp.login(self.config.username, self.config.password)
        smtp.send_message(message)
