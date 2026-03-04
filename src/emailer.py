"""Gmail SMTP email sender for funding digests."""

from __future__ import annotations

import logging
import os
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader

logger = logging.getLogger(__name__)


class Emailer:
    """Send HTML funding digest emails via Gmail SMTP."""

    def __init__(
        self,
        smtp_host: str = "smtp.gmail.com",
        smtp_port: int = 587,
        use_tls: bool = True,
        template_dir: str = "templates",
        archive_dir: str = "outputs/digests",
    ) -> None:
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.use_tls = use_tls
        self.sender = os.environ.get("GMAIL_ADDRESS", "")
        self.password = os.environ.get("GMAIL_APP_PASSWORD", "")
        self.archive_dir = Path(archive_dir)
        self.archive_dir.mkdir(parents=True, exist_ok=True)

        self.jinja_env = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=True,
        )

    def compose(
        self,
        government_opps: list[dict],
        industry_opps: list[dict],
        upcoming_deadlines: list[dict],
        date_str: Optional[str] = None,
    ) -> str:
        """Compose HTML digest from template.

        Args:
            government_opps: Government opportunities grouped by source.
            industry_opps: Industry opportunities grouped by source.
            upcoming_deadlines: Opportunities with upcoming deadlines.
            date_str: Date string for the subject line.

        Returns:
            Rendered HTML string.
        """
        if date_str is None:
            date_str = datetime.now().strftime("%B %d, %Y")

        total_count = len(government_opps) + len(industry_opps)

        # Group government by source
        gov_grouped: dict[str, list[dict]] = {}
        for opp in government_opps:
            source = opp.get("source", "unknown")
            gov_grouped.setdefault(source, []).append(opp)

        # Group industry by source
        ind_grouped: dict[str, list[dict]] = {}
        for opp in industry_opps:
            source = opp.get("source", "unknown")
            ind_grouped.setdefault(source, []).append(opp)

        template = self.jinja_env.get_template("digest.html")
        html = template.render(
            date=date_str,
            total_count=total_count,
            government_groups=gov_grouped,
            industry_groups=ind_grouped,
            upcoming_deadlines=upcoming_deadlines,
            deadline_count=len(upcoming_deadlines),
        )

        return html

    def send(
        self,
        recipient: str,
        subject: str,
        html_body: str,
    ) -> bool:
        """Send an HTML email via Gmail SMTP.

        Args:
            recipient: Email address of the recipient.
            subject: Email subject line.
            html_body: HTML content of the email.

        Returns:
            True if sent successfully.
        """
        if not self.sender or not self.password:
            logger.error("Gmail credentials not configured (GMAIL_ADDRESS, GMAIL_APP_PASSWORD)")
            return False

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.sender
        msg["To"] = recipient

        # Plain text fallback
        plain = "This email requires HTML to view. Please enable HTML in your email client."
        msg.attach(MIMEText(plain, "plain"))
        msg.attach(MIMEText(html_body, "html"))

        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                if self.use_tls:
                    server.starttls()
                server.login(self.sender, self.password)
                server.sendmail(self.sender, recipient, msg.as_string())

            logger.info(f"Email sent to {recipient}: {subject}")
            return True

        except Exception:
            logger.exception(f"Failed to send email to {recipient}")
            return False

    def archive_digest(self, html_body: str, date_str: Optional[str] = None) -> Path:
        """Save digest HTML to archive directory."""
        if date_str is None:
            date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self.archive_dir / f"digest_{date_str}.html"
        path.write_text(html_body, encoding="utf-8")
        logger.info(f"Digest archived to {path}")
        return path
