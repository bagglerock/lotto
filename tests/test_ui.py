from pathlib import Path

from streamlit.testing.v1 import AppTest
from streamlit.web.server.starlette.starlette_gzip_middleware import (
    _MediaAwareGZipResponder,
)

from lotto_lab.data import Database
from lotto_lab.ui.charts import match_distribution_chart_spec


def test_streamlit_gzip_responder_is_compatible_with_starlette() -> None:
    async def app(scope, receive, send) -> None:
        return None

    responder = _MediaAwareGZipResponder(app, 500, compresslevel=9)

    assert responder.minimum_size == 500


def test_match_distribution_chart_labels_and_preserves_small_values() -> None:
    spec = match_distribution_chart_spec()

    assert spec["encoding"]["x"]["axis"]["title"] == "Number of matches"
    assert spec["encoding"]["y"]["axis"]["title"] == "Number of tickets"
    assert spec["encoding"]["y"]["scale"]["type"] == "symlog"
    assert spec["layer"][1]["encoding"]["text"]["field"] == "Number of tickets"


def test_streamlit_app_renders_with_local_data(tmp_path, monkeypatch, powerball_draws) -> None:
    monkeypatch.setenv("LOTTO_LAB_DATA_DIR", str(tmp_path))
    database = Database(tmp_path / "lotto.db")
    database.upsert_draws(powerball_draws)
    app_path = Path(__file__).parents[1] / "src" / "lotto_lab" / "ui" / "app.py"

    app = AppTest.from_file(str(app_path), default_timeout=10).run()

    assert not app.exception
    assert app.title[0].value == "Lotto Lab"
    assert app.radio[0].value == "Powerball"
