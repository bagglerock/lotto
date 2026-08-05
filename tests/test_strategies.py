import numpy as np
import pytest

from lotto_lab.strategies import STRATEGIES, inclusion_probabilities, normalize


def test_normalize_falls_back_to_uniform() -> None:
    assert np.allclose(normalize(np.zeros(4)), np.full(4, 0.25))


def test_inclusion_probabilities_are_bounded_and_sum_to_selection_count() -> None:
    probabilities = inclusion_probabilities(np.asarray([100.0, 1.0, 1.0, 1.0]), 2)
    assert np.all(probabilities >= 0)
    assert np.all(probabilities <= 1)
    assert probabilities.sum() == pytest.approx(2.0)


@pytest.mark.parametrize("slug", list(STRATEGIES))
def test_every_strategy_generates_valid_deterministic_tickets(
    slug, powerball_draws, powerball_rules
) -> None:
    strategy = STRATEGIES[slug]
    first = strategy.generate(
        powerball_draws, powerball_rules, 10, np.random.default_rng(99)
    )
    second = strategy.generate(
        powerball_draws, powerball_rules, 10, np.random.default_rng(99)
    )
    assert first == second
    for ticket in first:
        assert len(ticket.white) == powerball_rules.white_count
        assert len(set(ticket.white)) == powerball_rules.white_count
        assert min(ticket.white) >= 1
        assert max(ticket.white) <= powerball_rules.white_max
        assert 1 <= ticket.special <= powerball_rules.special_max


@pytest.mark.parametrize("slug", list(STRATEGIES))
def test_every_strategy_returns_valid_scores(slug, powerball_draws, powerball_rules) -> None:
    scores = STRATEGIES[slug].score(powerball_draws, powerball_rules)
    assert scores.white.shape == (powerball_rules.white_max,)
    assert scores.special.shape == (powerball_rules.special_max,)
    assert np.all(np.isfinite(scores.white))
    assert np.all(np.isfinite(scores.special))
    assert np.all(scores.white >= 0)
    assert np.all(scores.special >= 0)

