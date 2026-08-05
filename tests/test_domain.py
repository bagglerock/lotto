from datetime import date

import pytest

from lotto_lab.domain import GAME_RULES, Draw, Game, parse_game


def test_current_rule_eras_are_explicit() -> None:
    assert GAME_RULES[Game.POWERBALL].effective_date == date(2015, 10, 7)
    assert GAME_RULES[Game.MEGA_MILLIONS].effective_date == date(2025, 4, 8)


def test_rule_validation_rejects_duplicate_white_balls() -> None:
    rules = GAME_RULES[Game.POWERBALL]
    draw = Draw(Game.POWERBALL, date(2026, 1, 1), (1, 2, 3, 4, 4), 5)
    with pytest.raises(ValueError, match="unique"):
        rules.validate(draw)


def test_next_draw_date_uses_game_schedule() -> None:
    powerball = GAME_RULES[Game.POWERBALL]
    mega = GAME_RULES[Game.MEGA_MILLIONS]
    assert powerball.next_draw_date(date(2026, 8, 5)) == date(2026, 8, 8)
    assert mega.next_draw_date(date(2026, 8, 5)) == date(2026, 8, 7)
    assert powerball.draw_date_on_or_after(date(2026, 8, 5)) == date(2026, 8, 5)


@pytest.mark.parametrize(
    ("value", "expected"),
    [("PB", Game.POWERBALL), ("powerball", Game.POWERBALL), ("Mega Millions", Game.MEGA_MILLIONS)],
)
def test_parse_game_aliases(value: str, expected: Game) -> None:
    assert parse_game(value) == expected
