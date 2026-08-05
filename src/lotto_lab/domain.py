from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum


class Game(StrEnum):
    POWERBALL = "powerball"
    MEGA_MILLIONS = "mega-millions"

    @property
    def display_name(self) -> str:
        return {
            Game.POWERBALL: "Powerball",
            Game.MEGA_MILLIONS: "Mega Millions",
        }[self]


@dataclass(frozen=True, slots=True)
class GameRules:
    game: Game
    effective_date: date
    white_max: int
    white_count: int
    special_max: int
    draw_weekdays: tuple[int, ...]
    dataset_id: str
    source_url: str
    low_confidence_below: int

    def validate(self, draw: Draw) -> None:
        if draw.game != self.game:
            raise ValueError(f"Expected {self.game}, received {draw.game}")
        if draw.draw_date < self.effective_date:
            raise ValueError(f"{draw.draw_date} predates the current {self.game} rules")
        if len(draw.white) != self.white_count:
            raise ValueError(f"Expected {self.white_count} white balls")
        if len(set(draw.white)) != self.white_count:
            raise ValueError("White balls must be unique")
        if tuple(sorted(draw.white)) != draw.white:
            raise ValueError("White balls must be stored in ascending order")
        if any(number < 1 or number > self.white_max for number in draw.white):
            raise ValueError(f"White balls must be between 1 and {self.white_max}")
        if draw.special < 1 or draw.special > self.special_max:
            raise ValueError(f"Special ball must be between 1 and {self.special_max}")

    def next_draw_date(self, after: date) -> date:
        candidate = after + timedelta(days=1)
        while candidate.weekday() not in self.draw_weekdays:
            candidate += timedelta(days=1)
        return candidate

    def draw_date_on_or_after(self, candidate: date) -> date:
        while candidate.weekday() not in self.draw_weekdays:
            candidate += timedelta(days=1)
        return candidate


@dataclass(frozen=True, slots=True)
class Draw:
    game: Game
    draw_date: date
    white: tuple[int, ...]
    special: int
    multiplier: int | None = None


@dataclass(frozen=True, slots=True)
class Ticket:
    game: Game
    white: tuple[int, ...]
    special: int


GAME_RULES: dict[Game, GameRules] = {
    Game.POWERBALL: GameRules(
        game=Game.POWERBALL,
        effective_date=date(2015, 10, 7),
        white_max=69,
        white_count=5,
        special_max=26,
        draw_weekdays=(0, 2, 5),
        dataset_id="d6yy-54nr",
        source_url="https://data.ny.gov/resource/d6yy-54nr.json",
        low_confidence_below=500,
    ),
    Game.MEGA_MILLIONS: GameRules(
        game=Game.MEGA_MILLIONS,
        effective_date=date(2025, 4, 8),
        white_max=70,
        white_count=5,
        special_max=24,
        draw_weekdays=(1, 4),
        dataset_id="5xaw-6ayf",
        source_url="https://data.ny.gov/resource/5xaw-6ayf.json",
        low_confidence_below=500,
    ),
}


def parse_game(value: str) -> Game:
    normalized = value.strip().lower().replace("_", "-").replace(" ", "-")
    aliases = {
        "pb": Game.POWERBALL,
        "powerball": Game.POWERBALL,
        "mm": Game.MEGA_MILLIONS,
        "mega": Game.MEGA_MILLIONS,
        "mega-millions": Game.MEGA_MILLIONS,
    }
    try:
        return aliases[normalized]
    except KeyError as exc:
        raise ValueError(f"Unknown game: {value}") from exc
