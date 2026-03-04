"""Stage 2: Weekly email pipeline.

Runs every Thursday at 8:00 PM. Queries SQLite for pending opportunities,
composes HTML digest, and sends via Gmail SMTP.

Usage:
    uv run python -m src.weekly_email
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from omegaconf import DictConfig, OmegaConf

from src.emailer import Emailer
from src.state import StateDB
from src.utils import setup_logging

logger = logging.getLogger(__name__)


def load_config() -> DictConfig:
    """Load Hydra config from conf/ directory."""
    cfg = OmegaConf.load("conf/config.yaml")
    for extra in ["conf/sources/government.yaml", "conf/sources/industry.yaml",
                   "conf/filter.yaml", "conf/email.yaml"]:
        if Path(extra).exists():
            cfg = OmegaConf.merge(cfg, OmegaConf.load(extra))
    return cfg


def run_pipeline(cfg: DictConfig) -> None:
    """Execute the weekly email pipeline."""
    db = StateDB(cfg.project.db_path)
    email_cfg = cfg.get("email", {})

    # Step 1: Query pending opportunities
    pending = db.get_pending_opportunities()
    logger.info(f"Found {len(pending)} pending opportunities")

    # Step 2: Query upcoming deadlines
    lookahead = email_cfg.get("deadline_lookahead_days", 30)
    upcoming = db.get_upcoming_deadlines(days=lookahead)
    logger.info(f"Found {len(upcoming)} upcoming deadlines (next {lookahead} days)")

    if not pending and not upcoming:
        logger.info("No opportunities or deadlines to email, skipping")
        db.record_email(count=0, success=True)
        db.close()
        return

    # Step 3: Split pending by source type
    gov_opps = [o for o in pending if o.get("source_type") == "government"]
    ind_opps = [o for o in pending if o.get("source_type") == "industry"]

    # Step 4: Compose email
    emailer = Emailer(
        smtp_host=email_cfg.get("smtp_host", "smtp.gmail.com"),
        smtp_port=email_cfg.get("smtp_port", 587),
        use_tls=email_cfg.get("use_tls", True),
        archive_dir=email_cfg.get("digest_archive_dir", "outputs/digests"),
    )

    date_str = datetime.now().strftime("%B %d, %Y")
    html = emailer.compose(
        government_opps=gov_opps,
        industry_opps=ind_opps,
        upcoming_deadlines=upcoming,
        date_str=date_str,
    )

    # Step 5: Send email
    total_count = len(pending)
    subject = f"{email_cfg.get('subject_prefix', 'Funding Digest')}: {date_str} ({total_count} opportunit{'y' if total_count == 1 else 'ies'})"
    recipient = email_cfg.get("recipient", "bo.yu@utah.edu")

    success = emailer.send(recipient=recipient, subject=subject, html_body=html)

    if success:
        # Step 6: Mark as emailed
        composite_ids = [o["composite_id"] for o in pending]
        db.mark_emailed(composite_ids)
        logger.info(f"Marked {len(composite_ids)} opportunities as emailed")

        # Archive digest
        emailer.archive_digest(html)
    else:
        logger.error("Email send failed")

    # Step 7: Record email
    db.record_email(count=total_count, success=success)
    db.close()


def main() -> None:
    load_dotenv()
    setup_logging("weekly_email")
    cfg = load_config()
    logger.info("Starting weekly email pipeline")

    try:
        run_pipeline(cfg)
        logger.info("Weekly email completed successfully")
    except Exception:
        logger.exception("Weekly email failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
