"""Static history page generator for emailed opportunities."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from src.state import StateDB

logger = logging.getLogger(__name__)


class HistoryGenerator:
    """Generate a browsable HTML page of all emailed opportunities."""

    def __init__(
        self,
        template_dir: str = "templates",
        output_dir: str = "outputs/history",
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.jinja_env = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=True,
        )

    def generate(self, db: StateDB) -> Path:
        """Generate history page from all emailed opportunities.

        Args:
            db: StateDB instance to query emailed opportunities.

        Returns:
            Path to the generated index.html file.
        """
        opps = db.get_emailed_opportunities()

        # Group by month (YYYY-MM from fetched_at)
        months: dict[str, list[dict]] = defaultdict(list)
        for opp in opps:
            fetched = opp.get("fetched_at", "")
            if fetched:
                try:
                    dt = datetime.fromisoformat(fetched)
                    month_key = dt.strftime("%Y-%m")
                except (ValueError, TypeError):
                    month_key = "Unknown"
            else:
                month_key = "Unknown"
            months[month_key].append(opp)

        # Sort months newest first
        sorted_months = sorted(months.items(), key=lambda x: x[0], reverse=True)

        # Format month labels
        month_groups = []
        for month_key, month_opps in sorted_months:
            if month_key != "Unknown":
                try:
                    label = datetime.strptime(month_key, "%Y-%m").strftime("%B %Y")
                except ValueError:
                    label = month_key
            else:
                label = "Unknown Date"
            month_groups.append({"label": label, "opportunities": month_opps})

        template = self.jinja_env.get_template("history.html")
        html = template.render(
            total_count=len(opps),
            last_updated=datetime.now().strftime("%B %d, %Y at %I:%M %p"),
            month_groups=month_groups,
        )

        output_path = self.output_dir / "index.html"
        output_path.write_text(html, encoding="utf-8")
        logger.info(f"History page generated: {output_path} ({len(opps)} opportunities)")
        return output_path
