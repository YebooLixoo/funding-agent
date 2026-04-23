"""Static history page generator for emailed opportunities."""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

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

    def generate(self, source) -> Path:
        """Generate history page from all emailed opportunities.

        Args:
            source: Any object implementing the ``HistoryDataSource`` protocol —
                i.e. exposing ``get_emailed_opportunities() -> list[dict]``.
                Concrete implementations include the legacy ``src.state.StateDB``
                and ``web.services.history_data_source.PlatformDBSource``.

        Returns:
            Path to the generated index.html file.
        """
        opps = source.get_emailed_opportunities()

        # Compute deadline metadata for each opportunity
        now = datetime.now(timezone.utc)
        sources_set = set()
        for opp in opps:
            # Parse deadline and compute days remaining
            deadline_str = opp.get("deadline", "")
            if deadline_str:
                try:
                    dl = datetime.fromisoformat(deadline_str)
                    if dl.tzinfo is None:
                        dl = dl.replace(tzinfo=timezone.utc)
                    delta = (dl - now).days
                    opp["days_until_deadline"] = delta
                    opp["deadline_date"] = dl.strftime("%Y-%m-%d")
                except (ValueError, TypeError):
                    opp["days_until_deadline"] = None
                    opp["deadline_date"] = ""
            else:
                opp["days_until_deadline"] = None
                opp["deadline_date"] = ""

            # Ensure deadline_type has a safe default
            opp.setdefault("deadline_type", "fixed")

            # Parse funding amount as numeric for sorting
            opp["funding_numeric"] = self._parse_funding_amount(opp.get("funding_amount", ""))

            # Collect sources
            sources_set.add(opp.get("source", "unknown"))

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
            sources=sorted(sources_set),
        )

        output_path = self.output_dir / "index.html"
        output_path.write_text(html, encoding="utf-8")
        logger.info(f"History page generated: {output_path} ({len(opps)} opportunities)")
        return output_path

    @staticmethod
    def _parse_funding_amount(amount_str: str) -> float:
        """Parse funding amount string to a numeric value for sorting."""
        if not amount_str:
            return 0.0
        # Remove $ and commas
        cleaned = re.sub(r'[$,]', '', amount_str)
        # Look for numbers with multipliers
        match = re.search(r'([\d.]+)\s*([MmBbKk])?', cleaned)
        if match:
            num = float(match.group(1))
            mult = (match.group(2) or '').upper()
            if mult == 'M':
                return num * 1_000_000
            elif mult == 'B':
                return num * 1_000_000_000
            elif mult == 'K':
                return num * 1_000
            return num
        return 0.0
