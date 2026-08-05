from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date

import numpy as np

from lotto_lab.domain import Draw, GameRules
from lotto_lab.strategies import Strategy, inclusion_probabilities, normalize

RECORDED_TICKETS_PER_DRAW = 10


@dataclass(frozen=True, slots=True)
class TicketOutcome:
    white: tuple[int, ...]
    special: int
    white_matches: int
    special_match: bool


@dataclass(frozen=True, slots=True)
class DrawBacktestResult:
    target_date: str
    training_cutoff: str
    training_draws: int
    actual_white: tuple[int, ...]
    actual_special: int
    tickets_evaluated: int
    white_match_distribution: dict[int, int]
    special_matches: int
    best_white_matches: int
    jackpot_hits: int
    top_tickets: tuple[TicketOutcome, ...]


@dataclass(frozen=True, slots=True)
class BacktestResult:
    strategy: str
    strategy_version: str
    draws_tested: int
    tickets_evaluated: int
    min_training_draws: int
    tickets_per_draw: int
    simulations: int
    average_white_matches: float
    random_expected_white_matches: float
    white_match_lift_percent: float
    special_match_rate: float
    random_expected_special_rate: float
    special_match_lift_percent: float
    top_ranked_white_hits_per_draw: float
    white_brier_score: float
    random_white_brier_score: float
    special_brier_score: float
    random_special_brier_score: float
    white_match_distribution: dict[int, int]
    jackpot_hits: int
    white_lift_ci_95: tuple[float, float]
    draw_results: tuple[DrawBacktestResult, ...]

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def run_backtest(
    draws: list[Draw],
    rules: GameRules,
    strategy: Strategy,
    *,
    min_training_draws: int = 100,
    tickets_per_draw: int = 10,
    simulations: int = 20,
    seed: int = 20260805,
    test_from: date | None = None,
) -> BacktestResult:
    if len(draws) <= min_training_draws:
        raise ValueError(
            f"Need more than {min_training_draws} drawings; only {len(draws)} are available"
        )
    if tickets_per_draw < 1 or simulations < 1:
        raise ValueError("Ticket and simulation counts must be positive")
    if any(
        first.draw_date >= second.draw_date
        for first, second in zip(draws, draws[1:], strict=False)
    ):
        raise ValueError("Draws must be strictly ordered by date")

    start_index = min_training_draws
    if test_from is not None:
        matching_indices = [
            index for index, draw in enumerate(draws) if draw.draw_date >= test_from
        ]
        if not matching_indices:
            raise ValueError(f"No drawing exists on or after the test date {test_from}")
        start_index = max(start_index, matching_indices[0])
    if start_index >= len(draws):
        raise ValueError("The selected test period has no drawings to evaluate")

    rng = np.random.default_rng(seed)
    distribution = {matches: 0 for matches in range(rules.white_count + 1)}
    total_white_matches = 0
    total_special_matches = 0
    jackpot_hits = 0
    white_brier_sum = 0.0
    special_brier_sum = 0.0
    top_hits = 0
    per_draw_white_matches: list[float] = []
    draw_results: list[DrawBacktestResult] = []

    for index in range(start_index, len(draws)):
        history = draws[:index]
        actual = draws[index]
        scores = strategy.score(history, rules)
        white_probability = inclusion_probabilities(scores.white, rules.white_count)
        special_probability = normalize(scores.special)

        white_actual = np.zeros(rules.white_max)
        white_actual[np.asarray(actual.white) - 1] = 1.0
        white_brier_sum += float(np.mean(np.square(white_probability - white_actual)))
        special_actual = np.zeros(rules.special_max)
        special_actual[actual.special - 1] = 1.0
        special_brier_sum += float(np.mean(np.square(special_probability - special_actual)))

        ranked = np.argsort(scores.white)[-rules.white_count :] + 1
        top_hits += len(set(int(value) for value in ranked) & set(actual.white))

        draw_match_total = 0
        ticket_count = tickets_per_draw * simulations
        tickets = strategy.generate_from_scores(scores, rules, ticket_count, rng)
        draw_distribution = {matches: 0 for matches in range(rules.white_count + 1)}
        draw_special_matches = 0
        draw_jackpot_hits = 0
        ticket_outcomes: list[TicketOutcome] = []
        for ticket in tickets:
            white_matches = len(set(ticket.white) & set(actual.white))
            special_match = ticket.special == actual.special
            distribution[white_matches] += 1
            draw_distribution[white_matches] += 1
            total_white_matches += white_matches
            draw_match_total += white_matches
            total_special_matches += int(special_match)
            draw_special_matches += int(special_match)
            is_jackpot = white_matches == rules.white_count and special_match
            jackpot_hits += int(is_jackpot)
            draw_jackpot_hits += int(is_jackpot)
            ticket_outcomes.append(
                TicketOutcome(
                    white=ticket.white,
                    special=ticket.special,
                    white_matches=white_matches,
                    special_match=special_match,
                )
            )
        ticket_outcomes.sort(
            key=lambda outcome: (outcome.white_matches, outcome.special_match),
            reverse=True,
        )
        draw_results.append(
            DrawBacktestResult(
                target_date=actual.draw_date.isoformat(),
                training_cutoff=history[-1].draw_date.isoformat(),
                training_draws=len(history),
                actual_white=actual.white,
                actual_special=actual.special,
                tickets_evaluated=ticket_count,
                white_match_distribution=draw_distribution,
                special_matches=draw_special_matches,
                best_white_matches=ticket_outcomes[0].white_matches,
                jackpot_hits=draw_jackpot_hits,
                top_tickets=tuple(ticket_outcomes[:RECORDED_TICKETS_PER_DRAW]),
            )
        )
        per_draw_white_matches.append(draw_match_total / ticket_count)

    draws_tested = len(draws) - start_index
    tickets_evaluated = draws_tested * tickets_per_draw * simulations
    average_white = total_white_matches / tickets_evaluated
    expected_white = rules.white_count**2 / rules.white_max
    special_rate = total_special_matches / tickets_evaluated
    expected_special = 1.0 / rules.special_max

    bootstrap_rng = np.random.default_rng(seed + 1)
    samples = np.asarray(per_draw_white_matches) - expected_white
    if len(samples) > 1:
        bootstrapped = np.asarray(
            [
                bootstrap_rng.choice(samples, size=len(samples), replace=True).mean()
                for _ in range(2000)
            ]
        )
        lower, upper = np.quantile(bootstrapped, [0.025, 0.975])
    else:
        lower = upper = float(samples[0])

    baseline_white_probability = rules.white_count / rules.white_max
    baseline_white_brier = baseline_white_probability * (1.0 - baseline_white_probability)
    baseline_special_probability = 1.0 / rules.special_max
    baseline_special_brier = baseline_special_probability * (
        1.0 - baseline_special_probability
    )

    return BacktestResult(
        strategy=strategy.name,
        strategy_version=strategy.version,
        draws_tested=draws_tested,
        tickets_evaluated=tickets_evaluated,
        min_training_draws=start_index,
        tickets_per_draw=tickets_per_draw,
        simulations=simulations,
        average_white_matches=average_white,
        random_expected_white_matches=expected_white,
        white_match_lift_percent=(average_white / expected_white - 1.0) * 100.0,
        special_match_rate=special_rate,
        random_expected_special_rate=expected_special,
        special_match_lift_percent=(special_rate / expected_special - 1.0) * 100.0,
        top_ranked_white_hits_per_draw=top_hits / draws_tested,
        white_brier_score=white_brier_sum / draws_tested,
        random_white_brier_score=baseline_white_brier,
        special_brier_score=special_brier_sum / draws_tested,
        random_special_brier_score=baseline_special_brier,
        white_match_distribution=distribution,
        jackpot_hits=jackpot_hits,
        white_lift_ci_95=(float(lower), float(upper)),
        draw_results=tuple(draw_results),
    )
