"""SMTP text/HTML mail with MIME attachments and TLS."""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage

from pydantic import BaseModel, Field, SecretStr, model_validator

from yuanboot.configuration import Configuration


class SmtpOptions(BaseModel):
    host: str = "localhost"
    port: int = Field(default=587, ge=1, le=65535)
    username: str = ""
    password: SecretStr = SecretStr("")
    starttls: bool = True
    ssl: bool = False
    timeout: float = Field(default=10, gt=0)

    @model_validator(mode="after")
    def validate_tls(self):
        if self.ssl and self.starttls:
            raise ValueError("Select ssl or starttls")
        return self


class SmtpClient:
    def __init__(self, options: SmtpOptions):
        self.options = options

    def send(
        self,
        sender: str,
        recipients: list[str] | str,
        subject: str,
        body: str,
        *,
        html=False,
        attachments: dict[str, bytes] | None = None,
    ):
        recipients = recipients.split(";") if isinstance(recipients, str) else recipients
        recipients = [recipient.strip() for recipient in recipients if recipient.strip()]
        if not recipients or any("@" not in value for value in [sender, *recipients]):
            raise ValueError("Sender and recipients must be email addresses")
        message = EmailMessage()
        message["From"], message["To"], message["Subject"] = sender, ", ".join(recipients), subject
        message.set_content(body, subtype="html" if html else "plain", charset="utf-8")
        for filename, data in (attachments or {}).items():
            message.add_attachment(
                data, maintype="application", subtype="octet-stream", filename=filename
            )
        options = self.options
        factory = smtplib.SMTP_SSL if options.ssl else smtplib.SMTP
        kwargs = {"context": ssl.create_default_context()} if options.ssl else {}
        with factory(options.host, options.port, timeout=options.timeout, **kwargs) as client:
            if options.starttls:
                client.starttls(context=ssl.create_default_context())
            if options.username:
                client.login(options.username, options.password.get_secret_value())
            return client.send_message(message, from_addr=sender, to_addrs=recipients)


def add_email(services):
    def factory(configuration: Configuration):
        return SmtpClient(SmtpOptions.model_validate(configuration.get("yuanboot.email", {})))

    services.add_singleton(SmtpClient, factory)
    return services
