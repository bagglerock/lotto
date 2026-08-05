from __future__ import annotations

from datetime import timedelta

import numpy as np
import pytest

from lotto_lab.domain import Draw, Game, GameRules


@pytest.fixture
def powerball_draws() -> list[Draw]:
    from lotto_lab.domain import GAME_RULES

    rules = GAME_RULES[Game.POWERBALL]
    rng = np.random.default_rng(42)
    draws: list[Draw] = []
    for index in range(140):
        white = tuple(
            sorted(int(value) for value in rng.choice(rules.white_max, 5, replace=False) + 1)
        )
        special = int(rng.integers(1, rules.special_max + 1))
        draws.append(
            Draw(
                game=rules.game,
                draw_date=rules.effective_date + timedelta(days=index + 1),
                white=white,
                special=special,
            )
        )
    return draws


@pytest.fixture
def powerball_rules() -> GameRules:
    from lotto_lab.domain import GAME_RULES

    return GAME_RULES[Game.POWERBALL]

