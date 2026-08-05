from __future__ import annotations

from datetime import date

import pandas as pd

from lotto_lab.backtest import DrawBacktestResult


def format_backtest_date(value: str) -> str:
    return date.fromisoformat(value).strftime("%b %d, %Y")


def draw_match_frame(result: DrawBacktestResult) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "White matches": list(result.white_match_distribution),
            "Tickets": list(result.white_match_distribution.values()),
        }
    )


def top_ticket_frame(result: DrawBacktestResult) -> pd.DataFrame:
    actual_white = set(result.actual_white)
    return pd.DataFrame(
        [
            {
                "Generated ticket": " ".join(f"{number:02d}" for number in ticket.white)
                + f"  ·  {ticket.special:02d}",
                "White matches": ticket.white_matches,
                "Matched white balls": " ".join(
                    f"{number:02d}" for number in ticket.white if number in actual_white
                )
                or "—",
                "Special match": "Yes" if ticket.special_match else "No",
            }
            for ticket in result.top_tickets
        ]
    )
