from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import date, timedelta

import numpy as np
import pandas as pd
import streamlit as st

from lotto_lab.backtest import run_backtest
from lotto_lab.data import Database, DataSourceError, NyOpenDataClient, sync_game
from lotto_lab.domain import GAME_RULES, Game
from lotto_lab.strategies import STRATEGIES, get_strategy, inclusion_probabilities
from lotto_lab.ui.charts import match_distribution_chart_spec


def database_argument() -> str | None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--database")
    arguments, _ = parser.parse_known_args()
    return arguments.database


@st.cache_resource
def database(path: str | None) -> Database:
    return Database(path)


def frequency_frame(draws, rules) -> pd.DataFrame:
    counts = Counter(number for draw in draws for number in draw.white)
    expected = len(draws) * rules.white_count / rules.white_max
    return pd.DataFrame(
        {
            "Number": range(1, rules.white_max + 1),
            "Drawn": [counts[number] for number in range(1, rules.white_max + 1)],
            "Expected": expected,
        }
    ).set_index("Number")


def render_ticket(ticket) -> str:
    white = "  ".join(f"{number:02d}" for number in ticket.white)
    return f"**{white}**  ·  **{ticket.special:02d}**"


st.set_page_config(page_title="Lotto Lab", page_icon="🎱", layout="wide")
st.title("Lotto Lab")
st.caption("Transparent strategies, walk-forward tests, and no claims of guaranteed prediction.")

db = database(database_argument())
selected_name = st.radio(
    "Game",
    [game.display_name for game in Game],
    horizontal=True,
    label_visibility="collapsed",
)
game = next(game for game in Game if game.display_name == selected_name)
rules = GAME_RULES[game]
draws = db.list_draws(game)

sync_column, status_column = st.columns([1, 4])
with sync_column:
    if st.button("Sync latest results", use_container_width=True):
        try:
            fetched, changed = sync_game(db, NyOpenDataClient(), game)
            st.success(f"Fetched {fetched}; stored or updated {changed}.")
            st.rerun()
        except DataSourceError as exc:
            st.error(str(exc))
with status_column:
    if draws:
        st.caption(
            f"{len(draws):,} current-format drawings · {rules.effective_date:%B %d, %Y} through "
            f"{draws[-1].draw_date:%B %d, %Y}"
        )
    else:
        st.warning("No local results yet. Sync the official data to begin.")

if not draws:
    st.stop()

if len(draws) < rules.low_confidence_below:
    st.warning(
        f"Young dataset: the current {game.display_name} format has only {len(draws):,} drawings. "
        "Frequency differences have low statistical confidence and should be treated as "
        "exploratory."
    )

overview_tab, generate_tab, backtest_tab, predictions_tab, data_tab = st.tabs(
    ["Overview", "Generate", "Backtest", "Locked Predictions", "Data"]
)

with overview_tab:
    first, second, third = st.columns(3)
    first.metric("Current-era drawings", f"{len(draws):,}")
    second.metric("Latest result", draws[-1].draw_date.strftime("%b %d, %Y"))
    second.caption(render_ticket(draws[-1]))
    earliest_target = max(date.today(), draws[-1].draw_date + timedelta(days=1))
    next_scheduled = rules.draw_date_on_or_after(earliest_target)
    third.metric("Next scheduled draw", next_scheduled.strftime("%b %d, %Y"))

    st.subheader("White-ball frequency")
    st.bar_chart(frequency_frame(draws, rules), color=["#E05260", "#8691A8"])
    st.caption(
        "Uneven bars are expected in random samples. The backtester determines whether a strategy "
        "built from these differences survives unseen future drawings."
    )

with generate_tab:
    strategy_slug = st.selectbox(
        "Algorithm",
        options=list(STRATEGIES),
        format_func=lambda slug: STRATEGIES[slug].name,
    )
    strategy = get_strategy(strategy_slug)
    st.caption(strategy.description)
    ticket_count = st.slider("Tickets", 1, 50, 5)
    seed = st.number_input("Reproducible seed", min_value=0, value=20260805, step=1)
    if st.button("Generate tickets", type="primary"):
        rng = np.random.default_rng(int(seed))
        generated = strategy.generate(draws, rules, ticket_count, rng)
        st.session_state["generated_tickets"] = generated
        st.session_state["generated_strategy"] = strategy_slug
        st.session_state["generated_seed"] = int(seed)
        st.session_state["generated_game"] = game.value

    generated = st.session_state.get("generated_tickets", [])
    if (
        generated
        and st.session_state.get("generated_strategy") == strategy_slug
        and st.session_state.get("generated_game") == game.value
    ):
        for index, ticket in enumerate(generated, 1):
            st.markdown(f"{index}. {render_ticket(ticket)}")
        target_date = st.date_input(
            "Target drawing",
            value=next_scheduled,
            min_value=date.today(),
        )
        if st.button("Lock this prediction"):
            try:
                prediction_id = db.save_prediction(
                    game=game,
                    target_date=target_date,
                    strategy=strategy.name,
                    strategy_version=f"{strategy.slug}:{strategy.version}",
                    data_cutoff=draws[-1].draw_date,
                    seed=st.session_state["generated_seed"],
                    parameters={"tickets": len(generated)},
                    tickets=generated,
                )
                st.success(f"Locked prediction #{prediction_id}. It will not be rewritten.")
            except Exception as exc:  # SQLite uniqueness is rendered as a useful UI message.
                st.error(f"Could not lock this prediction: {exc}")

    scores = strategy.score(draws, rules)
    probability = inclusion_probabilities(scores.white, rules.white_count)
    ranking = pd.DataFrame(
        {
            "Number": range(1, rules.white_max + 1),
            "Model inclusion score": probability,
        }
    ).sort_values("Model inclusion score", ascending=False)
    with st.expander("Why these numbers?"):
        st.dataframe(ranking, hide_index=True, use_container_width=True)

with backtest_tab:
    backtest_strategy_slug = st.selectbox(
        "Algorithm to test",
        options=list(STRATEGIES),
        format_func=lambda slug: STRATEGIES[slug].name,
        key="backtest_strategy",
    )
    earliest_index = min(20, len(draws) - 1)
    default_index = min(100, len(draws) - 1)
    test_from = st.date_input(
        "Pretend today was",
        value=draws[default_index].draw_date,
        min_value=draws[earliest_index].draw_date,
        max_value=draws[-1].draw_date,
    )
    training_count = next(
        index for index, draw in enumerate(draws) if draw.draw_date >= test_from
    )
    st.caption(
        f"The first prediction will train on {training_count:,} earlier drawings, then the "
        "model will move forward one drawing at a time."
    )
    ticket_column, simulation_column = st.columns(2)
    tickets_per_draw = ticket_column.slider("Tickets per historical draw", 1, 50, 10)
    simulations = simulation_column.slider("Repeated portfolios", 1, 100, 20)
    st.caption(
        "Each prediction sees only drawings that occurred before its target date. Repeated "
        "portfolios reduce the influence of one lucky random ticket."
    )
    if st.button("Run walk-forward backtest", type="primary"):
        with st.spinner("Walking forward through history…"):
            result = run_backtest(
                draws,
                rules,
                get_strategy(backtest_strategy_slug),
                min_training_draws=20,
                tickets_per_draw=tickets_per_draw,
                simulations=simulations,
                test_from=test_from,
            )
        metric_columns = st.columns(4)
        metric_columns[0].metric("Draws tested", f"{result.draws_tested:,}")
        metric_columns[1].metric("Virtual tickets", f"{result.tickets_evaluated:,}")
        metric_columns[2].metric(
            "White-match lift", f"{result.white_match_lift_percent:+.2f}%", help="Versus random"
        )
        metric_columns[3].metric(
            "Special-ball lift", f"{result.special_match_lift_percent:+.2f}%", help="Versus random"
        )
        lower, upper = result.white_lift_ci_95
        if lower <= 0 <= upper:
            st.info(
                "The 95% interval includes zero, so this result does not demonstrate an advantage "
                "over random selection."
            )
        else:
            st.warning(
                "The interval excludes zero in this backtest. This is interesting, but still needs "
                "locked forward testing before it should be treated as repeatable."
            )
        st.dataframe(
            pd.DataFrame(
                {
                    "Metric": ["White Brier score", "Special Brier score"],
                    "Algorithm": [result.white_brier_score, result.special_brier_score],
                    "Random baseline": [
                        result.random_white_brier_score,
                        result.random_special_brier_score,
                    ],
                }
            ),
            hide_index=True,
            use_container_width=True,
        )
        distribution = pd.DataFrame(
            {
                "Number of matches": list(result.white_match_distribution),
                "Number of tickets": list(result.white_match_distribution.values()),
            }
        )
        st.subheader("White-ball match distribution")
        st.vega_lite_chart(
            distribution,
            match_distribution_chart_spec(),
            width="stretch",
        )
        st.caption(
            "The vertical axis uses a symmetric logarithmic scale so rare three-, four-, or "
            "five-match tickets remain visible beside much larger counts. Labels show exact totals."
        )

with predictions_tab:
    predictions = db.list_predictions(game)
    draws_by_date = {draw.draw_date.isoformat(): draw for draw in draws}
    if not predictions:
        st.info("No locked predictions yet. Generate tickets and lock them before a drawing.")
    for prediction in predictions:
        with st.expander(
            f"{prediction['target_date']} · {prediction['strategy']} · seed {prediction['seed']}"
        ):
            st.caption(
                f"Data cutoff {prediction['data_cutoff']} · created {prediction['created_at']} · "
                f"version {prediction['strategy_version']}"
            )
            for index, ticket in enumerate(json.loads(prediction["tickets_json"]), 1):
                white = "  ".join(f"{number:02d}" for number in ticket["white"])
                result = draws_by_date.get(prediction["target_date"])
                score = ""
                if result:
                    white_matches = len(set(ticket["white"]) & set(result.white))
                    special_match = ticket["special"] == result.special
                    score = (
                        f" — {white_matches} white"
                        f"{' + special' if special_match else ''}"
                    )
                st.markdown(
                    f"{index}. **{white}** · **{ticket['special']:02d}**{score}"
                )

with data_tab:
    st.subheader("Current rules")
    st.json(
        {
            "game": game.display_name,
            "effective_date": rules.effective_date.isoformat(),
            "white_balls": f"{rules.white_count} from 1–{rules.white_max}",
            "special_ball": f"1 from 1–{rules.special_max}",
            "dataset_id": rules.dataset_id,
        }
    )
    draw_frame = pd.DataFrame(
        [
            {
                "Date": draw.draw_date,
                "White balls": " ".join(f"{value:02d}" for value in draw.white),
                "Special": draw.special,
                "Multiplier": draw.multiplier,
            }
            for draw in reversed(draws)
        ]
    )
    st.dataframe(draw_frame, hide_index=True, use_container_width=True)
