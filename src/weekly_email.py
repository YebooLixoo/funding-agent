"""Stage 2: Weekly email pipeline.

Runs every Thursday at 8:00 PM Mountain Time. Queries SQLite for pending opportunities,
composes HTML digest, and sends via Gmail SMTP.

Usage:
    uv run python -m src.weekly_email           # Production: send to all recipients
    uv run python -m src.weekly_email --test    # Test: send only to bo.yu@utah.edu
"""

from __future__ import annotations

import argparse
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


def run_pipeline(cfg: DictConfig, test_mode: bool = False) -> None:
    """Execute the weekly email pipeline.

    Args:
        cfg: Hydra configuration.
        test_mode: If True, send only to test_recipient instead of full list.
    """
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
    if test_mode:
        recipients = [email_cfg.get("test_recipient", "bo.yu@utah.edu")]
        subject = f"[TEST] {email_cfg.get('subject_prefix', 'Funding Digest')}: {date_str} ({total_count} opportunit{'y' if total_count == 1 else 'ies'})"
        logger.info(f"TEST MODE: sending only to {recipients[0]}")
    else:
        recipients = list(email_cfg.get("recipients", ["bo.yu@utah.edu"]))
        subject = f"{email_cfg.get('subject_prefix', 'Funding Digest')}: {date_str} ({total_count} opportunit{'y' if total_count == 1 else 'ies'})"

    success = emailer.send(recipients=recipients, subject=subject, html_body=html)

    if success:
        # Step 6: Mark as emailed (only in production mode)
        if not test_mode:
            composite_ids = [o["composite_id"] for o in pending]
            db.mark_emailed(composite_ids)
            logger.info(f"Marked {len(composite_ids)} opportunities as emailed")
        else:
            logger.info("TEST MODE: opportunities NOT marked as emailed")

        # Archive digest
        emailer.archive_digest(html)
    else:
        logger.error("Email send failed")

    # Step 7: Record email
    db.record_email(count=total_count, success=success)
    db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Weekly funding digest email")
    parser.add_argument(
        "--test", action="store_true",
        help="Test mode: send only to bo.yu@utah.edu, don't mark as emailed",
    )
    args = parser.parse_args()

    load_dotenv()
    setup_logging("weekly_email")
    cfg = load_config()

    mode_str = "TEST" if args.test else "PRODUCTION"
    logger.info(f"Starting weekly email pipeline ({mode_str})")

    try:
        run_pipeline(cfg, test_mode=args.test)
        logger.info("Weekly email completed successfully")
    except Exception:
        logger.exception("Weekly email failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
