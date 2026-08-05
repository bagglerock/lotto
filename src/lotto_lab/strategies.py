from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from lotto_lab.domain import Draw, GameRules, Ticket

FloatArray = NDArray[np.float64]


@dataclass(frozen=True, slots=True)
class StrategyScores:
    white: FloatArray
    special: FloatArray

    def __post_init__(self) -> None:
        if np.any(~np.isfinite(self.white)) or np.any(~np.isfinite(self.special)):
            raise ValueError("Strategy scores must be finite")
        if np.any(self.white < 0) or np.any(self.special < 0):
            raise ValueError("Strategy scores cannot be negative")
        if self.white.sum() <= 0 or self.special.sum() <= 0:
            raise ValueError("Strategy scores must contain positive weight")


def normalize(values: FloatArray) -> FloatArray:
    values = np.asarray(values, dtype=np.float64)
    total = values.sum()
    if not np.isfinite(total) or total <= 0:
        return np.full(len(values), 1.0 / len(values))
    return values / total


def inclusion_probabilities(weights: FloatArray, selections: int) -> FloatArray:
    """Convert sampling weights to bounded approximate marginal inclusion probabilities."""
    probabilities = np.zeros(len(weights), dtype=np.float64)
    remaining = np.ones(len(weights), dtype=bool)
    remaining_slots = float(selections)
    normalized = normalize(weights)

    while remaining_slots > 1e-12 and np.any(remaining):
        available = normalized[remaining]
        allocation = remaining_slots * available / available.sum()
        capped = allocation >= 1.0
        remaining_indices = np.flatnonzero(remaining)
        if not np.any(capped):
            probabilities[remaining_indices] = allocation
            break
        capped_indices = remaining_indices[capped]
        probabilities[capped_indices] = 1.0
        remaining[capped_indices] = False
        remaining_slots -= float(len(capped_indices))

    return probabilities


def _counts(draws: list[Draw], maximum: int, *, special: bool) -> FloatArray:
    values = np.zeros(maximum, dtype=np.float64)
    for draw in draws:
        numbers = (draw.special,) if special else draw.white
        for number in numbers:
            values[number - 1] += 1.0
    return values


def _bayesian_z_scores(
    draws: list[Draw], maximum: int, selections: int, prior_strength: float, *, special: bool
) -> FloatArray:
    count = _counts(draws, maximum, special=special)
    sample_size = len(draws)
    base_probability = selections / maximum
    posterior = (count + base_probability * prior_strength) / (sample_size + prior_strength)
    standard_error = np.sqrt(
        base_probability * (1.0 - base_probability) / max(sample_size + prior_strength, 1.0)
    )
    return (posterior - base_probability) / max(standard_error, 1e-12)


def _exp_weights(z_scores: FloatArray, direction: float, temperature: float) -> FloatArray:
    return np.exp(direction * temperature * np.clip(z_scores, -4.0, 4.0))


class Strategy(ABC):
    slug: str
    name: str
    version: str = "1.0"
    description: str

    @abstractmethod
    def score(self, draws: list[Draw], rules: GameRules) -> StrategyScores:
        raise NotImplementedError

    def generate(
        self,
        draws: list[Draw],
        rules: GameRules,
        count: int,
        rng: np.random.Generator,
    ) -> list[Ticket]:
        return self.generate_from_scores(self.score(draws, rules), rules, count, rng)

    def generate_from_scores(
        self,
        scores: StrategyScores,
        rules: GameRules,
        count: int,
        rng: np.random.Generator,
    ) -> list[Ticket]:
        if count < 1:
            raise ValueError("Ticket count must be positive")
        white_numbers = np.arange(1, rules.white_max + 1)
        special_numbers = np.arange(1, rules.special_max + 1)
        white_probability = normalize(scores.white)
        special_probability = normalize(scores.special)
        tickets: list[Ticket] = []
        for _ in range(count):
            white = tuple(
                sorted(
                    int(number)
                    for number in rng.choice(
                        white_numbers,
                        size=rules.white_count,
                        replace=False,
                        p=white_probability,
                    )
                )
            )
            special = int(rng.choice(special_numbers, p=special_probability))
            tickets.append(Ticket(rules.game, white, special))
        return tickets


class RandomStrategy(Strategy):
    slug = "random"
    name = "Pure Random"
    description = "Equal probability for every valid number; the control strategy."

    def score(self, draws: list[Draw], rules: GameRules) -> StrategyScores:
        return StrategyScores(np.ones(rules.white_max), np.ones(rules.special_max))


class BayesianHotStrategy(Strategy):
    slug = "bayesian-hot"
    name = "Bayesian Hot"
    description = "Favors frequent numbers while shrinking small-sample differences toward random."

    def __init__(self, prior_strength: float = 100.0, temperature: float = 0.35) -> None:
        self.prior_strength = prior_strength
        self.temperature = temperature

    def score(self, draws: list[Draw], rules: GameRules) -> StrategyScores:
        white_z = _bayesian_z_scores(
            draws, rules.white_max, rules.white_count, self.prior_strength, special=False
        )
        special_z = _bayesian_z_scores(
            draws, rules.special_max, 1, self.prior_strength, special=True
        )
        return StrategyScores(
            _exp_weights(white_z, 1.0, self.temperature),
            _exp_weights(special_z, 1.0, self.temperature),
        )


class BayesianColdStrategy(BayesianHotStrategy):
    slug = "bayesian-cold"
    name = "Bayesian Cold"
    description = "Favors infrequent numbers with the same small-sample protection."

    def score(self, draws: list[Draw], rules: GameRules) -> StrategyScores:
        white_z = _bayesian_z_scores(
            draws, rules.white_max, rules.white_count, self.prior_strength, special=False
        )
        special_z = _bayesian_z_scores(
            draws, rules.special_max, 1, self.prior_strength, special=True
        )
        return StrategyScores(
            _exp_weights(white_z, -1.0, self.temperature),
            _exp_weights(special_z, -1.0, self.temperature),
        )


class HotColdMixStrategy(BayesianHotStrategy):
    slug = "hot-cold-mix"
    name = "Hot/Cold Mix"
    description = "Favors both tails of the frequency distribution over average-frequency numbers."

    def score(self, draws: list[Draw], rules: GameRules) -> StrategyScores:
        white_z = _bayesian_z_scores(
            draws, rules.white_max, rules.white_count, self.prior_strength, special=False
        )
        special_z = _bayesian_z_scores(
            draws, rules.special_max, 1, self.prior_strength, special=True
        )
        return StrategyScores(
            np.exp(self.temperature * np.clip(np.abs(white_z), 0.0, 4.0)),
            np.exp(self.temperature * np.clip(np.abs(special_z), 0.0, 4.0)),
        )


class RecentTrendStrategy(Strategy):
    slug = "recent-trend"
    name = "Recent Trend"
    description = "Uses exponentially decaying weights so recent drawings matter more."

    def __init__(self, half_life: float = 25.0, prior_strength: float = 25.0) -> None:
        self.half_life = half_life
        self.prior_strength = prior_strength

    @staticmethod
    def _scores(
        draws: list[Draw],
        maximum: int,
        selections: int,
        half_life: float,
        prior: float,
        *,
        special: bool,
    ) -> FloatArray:
        ages = np.arange(len(draws) - 1, -1, -1, dtype=np.float64)
        draw_weights = np.power(0.5, ages / half_life)
        weighted_counts = np.zeros(maximum, dtype=np.float64)
        for draw, weight in zip(draws, draw_weights, strict=True):
            numbers = (draw.special,) if special else draw.white
            for number in numbers:
                weighted_counts[number - 1] += weight
        base = selections / maximum
        rate = (weighted_counts + base * prior) / (draw_weights.sum() + prior)
        relative = (rate - base) / base
        return np.exp(0.8 * np.clip(relative, -1.5, 1.5))

    def score(self, draws: list[Draw], rules: GameRules) -> StrategyScores:
        return StrategyScores(
            self._scores(
                draws,
                rules.white_max,
                rules.white_count,
                self.half_life,
                self.prior_strength,
                special=False,
            ),
            self._scores(
                draws,
                rules.special_max,
                1,
                self.half_life,
                self.prior_strength,
                special=True,
            ),
        )


class OverdueStrategy(Strategy):
    slug = "overdue"
    name = "Overdue"
    description = "Favors numbers whose current absence exceeds their theoretical average gap."

    @staticmethod
    def _gap_weights(
        draws: list[Draw], maximum: int, selections: int, *, special: bool
    ) -> FloatArray:
        gaps = np.full(maximum, len(draws), dtype=np.float64)
        unseen = set(range(1, maximum + 1))
        for age, draw in enumerate(reversed(draws)):
            numbers = (draw.special,) if special else draw.white
            for number in numbers:
                if number in unseen:
                    gaps[number - 1] = age
                    unseen.remove(number)
            if not unseen:
                break
        expected_gap = maximum / selections - 1.0
        relative = (gaps - expected_gap) / max(expected_gap, 1.0)
        return np.exp(0.55 * np.clip(relative, -1.0, 3.0))

    def score(self, draws: list[Draw], rules: GameRules) -> StrategyScores:
        return StrategyScores(
            self._gap_weights(draws, rules.white_max, rules.white_count, special=False),
            self._gap_weights(draws, rules.special_max, 1, special=True),
        )


class CombinedStrategy(Strategy):
    slug = "combined"
    name = "Combined Model"
    description = "Blends Bayesian frequency, recent trend, and gap scores geometrically."

    def __init__(self) -> None:
        self.components: tuple[tuple[Strategy, float], ...] = (
            (BayesianHotStrategy(), 0.40),
            (RecentTrendStrategy(), 0.35),
            (OverdueStrategy(), 0.25),
        )

    def score(self, draws: list[Draw], rules: GameRules) -> StrategyScores:
        white_log = np.zeros(rules.white_max)
        special_log = np.zeros(rules.special_max)
        for strategy, weight in self.components:
            scores = strategy.score(draws, rules)
            white_log += weight * np.log(np.maximum(normalize(scores.white), 1e-12))
            special_log += weight * np.log(np.maximum(normalize(scores.special), 1e-12))
        return StrategyScores(np.exp(white_log), np.exp(special_log))


STRATEGIES: dict[str, Strategy] = {
    strategy.slug: strategy
    for strategy in (
        RandomStrategy(),
        BayesianHotStrategy(),
        BayesianColdStrategy(),
        HotColdMixStrategy(),
        RecentTrendStrategy(),
        OverdueStrategy(),
        CombinedStrategy(),
    )
}


def get_strategy(slug: str) -> Strategy:
    try:
        return STRATEGIES[slug]
    except KeyError as exc:
        choices = ", ".join(STRATEGIES)
        raise ValueError(f"Unknown strategy '{slug}'. Choose one of: {choices}") from exc
