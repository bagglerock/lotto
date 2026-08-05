from datetime import date
from io import BytesIO
from urllib.error import HTTPError
from urllib.request import Request

import pytest

from lotto_lab.data import Database, NyOpenDataClient
from lotto_lab.domain import GAME_RULES, Draw, Game, Ticket


def test_parse_powerball_row() -> None:
    draw = NyOpenDataClient.parse_row(
        GAME_RULES[Game.POWERBALL],
        {
            "draw_date": "2026-08-03T00:00:00.000",
            "winning_numbers": "08 30 41 48 54 04",
            "multiplier": "2",
        },
    )
    assert draw.white == (8, 30, 41, 48, 54)
    assert draw.special == 4
    assert draw.multiplier == 2


def test_parse_mega_millions_row() -> None:
    draw = NyOpenDataClient.parse_row(
        GAME_RULES[Game.MEGA_MILLIONS],
        {
            "draw_date": "2026-08-04T00:00:00.000",
            "winning_numbers": "14 21 51 55 65",
            "mega_ball": "21",
        },
    )
    assert draw.white == (14, 21, 51, 55, 65)
    assert draw.special == 21
    assert draw.multiplier is None


def test_database_round_trip_and_locked_prediction(tmp_path) -> None:
    path = tmp_path / "test.db"
    database = Database(path)
    draw = Draw(Game.POWERBALL, date(2026, 8, 3), (8, 30, 41, 48, 54), 4, 2)
    assert database.upsert_draws([draw]) == 1
    assert database.list_draws(Game.POWERBALL) == [draw]
    assert database.latest_date(Game.POWERBALL) == date(2026, 8, 3)

    prediction_id = database.save_prediction(
        game=Game.POWERBALL,
        target_date=date(2026, 8, 5),
        strategy="Pure Random",
        strategy_version="random:1.0",
        data_cutoff=draw.draw_date,
        seed=123,
        parameters={"tickets": 1},
        tickets=[Ticket(Game.POWERBALL, (1, 2, 3, 4, 5), 6)],
    )
    assert prediction_id == 1
    saved = database.list_predictions(Game.POWERBALL)
    assert saved[0]["data_cutoff"] == "2026-08-03"
    assert '"special": 6' in saved[0]["tickets_json"]


def test_prediction_rejects_non_drawing_day(tmp_path) -> None:
    database = Database(tmp_path / "test.db")
    with pytest.raises(ValueError, match="not a scheduled"):
        database.save_prediction(
            game=Game.POWERBALL,
            target_date=date(2026, 8, 6),
            strategy="Pure Random",
            strategy_version="random:1.0",
            data_cutoff=date(2026, 8, 3),
            seed=123,
            parameters={"tickets": 1},
            tickets=[Ticket(Game.POWERBALL, (1, 2, 3, 4, 5), 6)],
        )


def test_api_retries_transient_server_errors(monkeypatch) -> None:
    attempts = 0

    def fake_urlopen(request, timeout):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise HTTPError(request.full_url, 502, "Bad Gateway", {}, None)
        return BytesIO(b"[]")

    monkeypatch.setattr("lotto_lab.data.urlopen", fake_urlopen)
    monkeypatch.setattr("lotto_lab.data.time.sleep", lambda _: None)
    client = NyOpenDataClient()

    assert client._read_json(Request("https://example.test"), Game.POWERBALL) == []
    assert attempts == 3
