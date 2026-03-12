"""Stage 2: Weekly email pipeline.

Runs every Thursday at 8:00 PM Mountain Time. Loads the pre-generated digest HTML
from the noon fetch pipeline and sends via Gmail SMTP.

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
from src.history_generator import HistoryGenerator
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

    # Step 1: Load pre-generated digest from noon pipeline
    emailer = Emailer(
        smtp_host=email_cfg.get("smtp_host", "smtp.gmail.com"),
        smtp_port=email_cfg.get("smtp_port", 587),
        use_tls=email_cfg.get("use_tls", True),
        archive_dir=email_cfg.get("digest_archive_dir", "outputs/digests"),
    )

    html = emailer.load_latest_digest(max_age_hours=12)
    if html is None:
        logger.error("No recent digest found — was the noon fetch pipeline run?")
        db.record_email(count=0, success=False)
        db.close()
        return

    # Step 2: Query pending count for subject line and mark_emailed
    pending = db.get_pending_opportunities()
    total_count = len(pending)
    logger.info(f"Found {total_count} pending opportunities to email")

    if total_count == 0:
        logger.info("No pending opportunities, skipping send")
        db.record_email(count=0, success=True)
        db.close()
        return

    # Step 3: Send email
    date_str = datetime.now().strftime("%B %d, %Y")
    if test_mode:
        recipients = [email_cfg.get("test_recipient", "bo.yu@utah.edu")]
        subject = f"[TEST] {email_cfg.get('subject_prefix', 'Funding Digest')}: {date_str} ({total_count} opportunit{'y' if total_count == 1 else 'ies'})"
        logger.info(f"TEST MODE: sending only to {recipients[0]}")
    else:
        recipients = list(email_cfg.get("recipients", ["bo.yu@utah.edu"]))
        subject = f"{email_cfg.get('subject_prefix', 'Funding Digest')}: {date_str} ({total_count} opportunit{'y' if total_count == 1 else 'ies'})"

    success = emailer.send(recipients=recipients, subject=subject, html_body=html)

    if success:
        # Step 4: Mark as emailed (only in production mode)
        if not test_mode:
            composite_ids = [o["composite_id"] for o in pending]
            db.mark_emailed(composite_ids)
            logger.info(f"Marked {len(composite_ids)} opportunities as emailed")
        else:
            logger.info("TEST MODE: opportunities NOT marked as emailed")
    else:
        logger.error("Email send failed")

    # Step 5: Record email
    db.record_email(count=total_count, success=success)

    # Step 6: Generate history page
    try:
        history_output_dir = email_cfg.get("history_output_dir", "outputs/history")
        history_gen = HistoryGenerator(output_dir=history_output_dir)
        history_gen.generate(db)
    except Exception:
        logger.exception("History page generation failed (non-fatal)")

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
