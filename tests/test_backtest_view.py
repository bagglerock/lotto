from lotto_lab.backtest import DrawBacktestResult, TicketOutcome
from lotto_lab.ui.backtest_view import (
    draw_match_frame,
    format_backtest_date,
    top_ticket_frame,
)


def test_backtest_view_explains_one_target_drawing() -> None:
    result = DrawBacktestResult(
        target_date="2021-08-04",
        training_cutoff="2021-08-02",
        training_draws=500,
        actual_white=(7, 18, 29, 39, 59),
        actual_special=14,
        tickets_evaluated=200,
        white_match_distribution={0: 130, 1: 60, 2: 9, 3: 1, 4: 0, 5: 0},
        special_matches=8,
        best_white_matches=3,
        jackpot_hits=0,
        top_tickets=(
            TicketOutcome(
                white=(7, 18, 29, 40, 60),
                special=14,
                white_matches=3,
                special_match=True,
            ),
        ),
    )

    counts = draw_match_frame(result)
    tickets = top_ticket_frame(result)

    assert format_backtest_date(result.target_date) == "Aug 04, 2021"
    assert counts.to_dict(orient="records")[3] == {"White matches": 3, "Tickets": 1}
    assert tickets.to_dict(orient="records") == [
        {
            "Generated ticket": "07 18 29 40 60  ·  14",
            "White matches": 3,
            "Matched white balls": "07 18 29",
            "Special match": "Yes",
        }
    ]
