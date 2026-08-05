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
