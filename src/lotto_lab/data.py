from __future__ import annotations

import json
import os
import sqlite3
import time
from collections.abc import Iterable
from datetime import UTC, date, datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from lotto_lab.domain import GAME_RULES, Draw, Game, GameRules, Ticket


class DataSourceError(RuntimeError):
    """Raised when a remote lottery dataset cannot be read or validated."""


class NyOpenDataClient:
    """Small Socrata client for the official NY Gaming Commission datasets."""

    def __init__(self, app_token: str | None = None, timeout: float = 20.0) -> None:
        self.app_token = app_token or os.getenv("SOCRATA_APP_TOKEN")
        self.timeout = timeout

    def fetch_draws(self, game: Game, after: date | None = None) -> list[Draw]:
        rules = GAME_RULES[game]
        if after is not None and after >= rules.effective_date:
            lower_bound = after
            comparator = ">"
        else:
            lower_bound = rules.effective_date
            comparator = ">="
        params = {
            "$where": f"draw_date {comparator} '{lower_bound.isoformat()}T00:00:00.000'",
            "$order": "draw_date ASC",
            "$limit": "5000",
        }
        request = Request(f"{rules.source_url}?{urlencode(params)}")
        request.add_header("Accept", "application/json")
        request.add_header("User-Agent", "lotto-lab/0.1")
        if self.app_token:
            request.add_header("X-App-Token", self.app_token)

        payload = self._read_json(request, game)

        if not isinstance(payload, list):
            raise DataSourceError("The lottery API returned an unexpected response")

        draws: list[Draw] = []
        for row in payload:
            try:
                draw = self.parse_row(rules, row)
                rules.validate(draw)
                draws.append(draw)
            except (KeyError, TypeError, ValueError) as exc:
                row_date = row.get("draw_date", "unknown") if isinstance(row, dict) else "unknown"
                raise DataSourceError(
                    f"Invalid {game.display_name} row at {row_date}: {exc}"
                ) from exc
        return draws

    def _read_json(self, request: Request, game: Game) -> object:
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                with urlopen(request, timeout=self.timeout) as response:  # noqa: S310
                    return json.load(response)
            except HTTPError as exc:
                last_error = exc
                if exc.code != 429 and exc.code < 500:
                    break
            except OSError as exc:
                last_error = exc
            except ValueError as exc:
                raise DataSourceError(
                    f"{game.display_name} returned invalid JSON: {exc}"
                ) from exc
            if attempt < 2:
                time.sleep(0.5 * (2**attempt))
        raise DataSourceError(
            f"Unable to fetch {game.display_name} results after 3 attempts: {last_error}"
        ) from last_error

    @staticmethod
    def parse_row(rules: GameRules, row: dict[str, str]) -> Draw:
        draw_date = date.fromisoformat(row["draw_date"][:10])
        values = tuple(int(value) for value in row["winning_numbers"].split())

        if rules.game == Game.POWERBALL:
            if len(values) != rules.white_count + 1:
                raise ValueError("Powerball winning_numbers must contain six values")
            white = tuple(sorted(values[: rules.white_count]))
            special = values[-1]
        else:
            if len(values) != rules.white_count:
                raise ValueError("Mega Millions winning_numbers must contain five values")
            white = tuple(sorted(values))
            special = int(row["mega_ball"])

        multiplier_value = row.get("multiplier")
        multiplier = int(multiplier_value) if multiplier_value else None
        return Draw(rules.game, draw_date, white, special, multiplier)


def default_database_path() -> Path:
    configured = os.getenv("LOTTO_LAB_DATA_DIR")
    directory = Path(configured).expanduser() if configured else Path.home() / ".lotto-lab"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / "lotto.db"


class Database:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else default_database_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS draws (
                    game TEXT NOT NULL,
                    draw_date TEXT NOT NULL,
                    white_json TEXT NOT NULL,
                    special INTEGER NOT NULL,
                    multiplier INTEGER,
                    source TEXT NOT NULL DEFAULT 'NY Open Data',
                    ingested_at TEXT NOT NULL,
                    PRIMARY KEY (game, draw_date)
                );

                CREATE TABLE IF NOT EXISTS predictions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    game TEXT NOT NULL,
                    target_date TEXT NOT NULL,
                    strategy TEXT NOT NULL,
                    strategy_version TEXT NOT NULL,
                    data_cutoff TEXT NOT NULL,
                    seed INTEGER NOT NULL,
                    parameters_json TEXT NOT NULL,
                    tickets_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE (game, target_date, strategy_version, seed)
                );
                """
            )

    def upsert_draws(self, draws: Iterable[Draw]) -> int:
        rows = list(draws)
        now = datetime.now(UTC).isoformat()
        with self.connect() as connection:
            before = connection.total_changes
            connection.executemany(
                """
                INSERT INTO draws (
                    game, draw_date, white_json, special, multiplier, ingested_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(game, draw_date) DO UPDATE SET
                    white_json = excluded.white_json,
                    special = excluded.special,
                    multiplier = excluded.multiplier,
                    ingested_at = excluded.ingested_at
                """,
                [
                    (
                        draw.game.value,
                        draw.draw_date.isoformat(),
                        json.dumps(draw.white),
                        draw.special,
                        draw.multiplier,
                        now,
                    )
                    for draw in rows
                ],
            )
            return connection.total_changes - before

    def list_draws(self, game: Game) -> list[Draw]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM draws WHERE game = ? ORDER BY draw_date ASC", (game.value,)
            ).fetchall()
        draws = [
            Draw(
                game=game,
                draw_date=date.fromisoformat(row["draw_date"]),
                white=tuple(json.loads(row["white_json"])),
                special=row["special"],
                multiplier=row["multiplier"],
            )
            for row in rows
        ]
        rules = GAME_RULES[game]
        for draw in draws:
            rules.validate(draw)
        return draws

    def latest_date(self, game: Game) -> date | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT MAX(draw_date) AS latest FROM draws WHERE game = ?", (game.value,)
            ).fetchone()
        return date.fromisoformat(row["latest"]) if row and row["latest"] else None

    def save_prediction(
        self,
        *,
        game: Game,
        target_date: date,
        strategy: str,
        strategy_version: str,
        data_cutoff: date,
        seed: int,
        parameters: dict[str, object],
        tickets: list[Ticket],
    ) -> int:
        if target_date <= data_cutoff:
            raise ValueError("Target date must be after the data cutoff")
        if not tickets:
            raise ValueError("At least one ticket is required")
        rules = GAME_RULES[game]
        if target_date.weekday() not in rules.draw_weekdays:
            raise ValueError(f"{target_date} is not a scheduled {game.display_name} drawing day")
        for ticket in tickets:
            if ticket.game != game:
                raise ValueError("Every ticket must belong to the prediction game")
            if (
                len(ticket.white) != rules.white_count
                or len(set(ticket.white)) != rules.white_count
            ):
                raise ValueError(
                    "Every ticket must contain the configured number of unique white balls"
                )
            if any(number < 1 or number > rules.white_max for number in ticket.white):
                raise ValueError("A ticket contains an out-of-range white ball")
            if ticket.special < 1 or ticket.special > rules.special_max:
                raise ValueError("A ticket contains an out-of-range special ball")
        created_at = datetime.now(UTC).isoformat()
        encoded_tickets = [
            {"white": list(ticket.white), "special": ticket.special} for ticket in tickets
        ]
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO predictions (
                    game, target_date, strategy, strategy_version, data_cutoff,
                    seed, parameters_json, tickets_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    game.value,
                    target_date.isoformat(),
                    strategy,
                    strategy_version,
                    data_cutoff.isoformat(),
                    seed,
                    json.dumps(parameters, sort_keys=True),
                    json.dumps(encoded_tickets),
                    created_at,
                ),
            )
            return int(cursor.lastrowid)

    def list_predictions(self, game: Game, limit: int = 50) -> list[dict[str, object]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM predictions
                WHERE game = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (game.value, limit),
            ).fetchall()
        return [dict(row) for row in rows]


def sync_game(database: Database, client: NyOpenDataClient, game: Game) -> tuple[int, int]:
    latest = database.latest_date(game)
    draws = client.fetch_draws(game, after=latest)
    changed = database.upsert_draws(draws)
    return len(draws), changed
