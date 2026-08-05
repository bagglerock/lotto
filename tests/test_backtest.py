import json

import pytest

from lotto_lab.backtest import run_backtest
from lotto_lab.strategies import RandomStrategy


def test_walk_forward_backtest_is_deterministic(powerball_draws, powerball_rules) -> None:
    kwargs = {
        "min_training_draws": 100,
        "tickets_per_draw": 3,
        "simulations": 2,
        "seed": 1234,
    }
    first = run_backtest(
        powerball_draws, powerball_rules, RandomStrategy(), **kwargs
    )
    second = run_backtest(
        powerball_draws, powerball_rules, RandomStrategy(), **kwargs
    )
    assert first == second
    assert first.draws_tested == 40
    assert first.tickets_evaluated == 240
    assert sum(first.white_match_distribution.values()) == 240
    assert first.random_expected_white_matches == pytest.approx(25 / 69)
    assert len(first.draw_results) == first.draws_tested
    first_target = first.draw_results[0]
    assert first_target.target_date == powerball_draws[100].draw_date.isoformat()
    assert first_target.training_cutoff == powerball_draws[99].draw_date.isoformat()
    assert first_target.training_draws == 100
    assert first_target.actual_white == powerball_draws[100].white
    assert first_target.actual_special == powerball_draws[100].special
    assert first_target.tickets_evaluated == 6
    assert sum(first_target.white_match_distribution.values()) == 6
    assert len(first_target.top_tickets) == 6
    assert first_target.best_white_matches == first_target.top_tickets[0].white_matches
    json.dumps(first.as_dict())


def test_backtest_rejects_insufficient_history(powerball_draws, powerball_rules) -> None:
    with pytest.raises(ValueError, match="Need more"):
        run_backtest(
            powerball_draws[:20],
            powerball_rules,
            RandomStrategy(),
            min_training_draws=20,
        )


def test_backtest_can_begin_at_a_historical_date(powerball_draws, powerball_rules) -> None:
    test_from = powerball_draws[120].draw_date
    result = run_backtest(
        powerball_draws,
        powerball_rules,
        RandomStrategy(),
        min_training_draws=20,
        tickets_per_draw=1,
        simulations=1,
        test_from=test_from,
    )
    assert result.min_training_draws == 120
    assert result.draws_tested == 20
    assert result.draw_results[0].target_date == test_from.isoformat()
    assert result.draw_results[0].training_cutoff == powerball_draws[119].draw_date.isoformat()
