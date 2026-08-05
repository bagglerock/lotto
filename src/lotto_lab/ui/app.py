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
from lotto_lab.ui.backtest_view import (
    draw_match_frame,
    format_backtest_date,
    top_ticket_frame,
)
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
    st.subheader("Walk-forward historical replay")
    st.info(
        "This does not test one fixed ticket against old drawings. It freezes history, generates "
        "new virtual tickets for the next real drawing, reveals that result, scores the tickets, "
        "and then repeats one drawing at a time."
    )
    backtest_strategy_slug = st.selectbox(
        "Algorithm to test",
        options=list(STRATEGIES),
        format_func=lambda slug: STRATEGIES[slug].name,
        key="backtest_strategy",
    )
    earliest_index = min(20, len(draws) - 1)
    default_index = min(100, len(draws) - 1)
    test_from = st.date_input(
        "Pretend today was (replay start)",
        value=draws[default_index].draw_date,
        min_value=draws[earliest_index].draw_date,
        max_value=draws[-1].draw_date,
        help="The first drawing on or after this date becomes the first unseen result to test.",
    )
    training_count = next(
        index for index, draw in enumerate(draws) if draw.draw_date >= test_from
    )
    ticket_column, simulation_column = st.columns(2)
    tickets_per_draw = ticket_column.slider(
        "Tickets per historical draw",
        1,
        50,
        10,
        help="How many new tickets the algorithm generates in each repeated portfolio.",
    )
    simulations = simulation_column.slider(
        "Repeated portfolios",
        1,
        100,
        20,
        help="Repeats ticket generation for each target drawing to reduce one lucky seed's effect.",
    )
    first_target = draws[training_count]
    first_training_cutoff = draws[training_count - 1]
    tickets_per_target = tickets_per_draw * simulations
    st.success(
        f"First replay: use {training_count:,} drawings through "
        f"{first_training_cutoff.draw_date:%b %d, %Y} → generate "
        f"{tickets_per_target:,} virtual tickets for {first_target.draw_date:%b %d, %Y} → "
        "compare them with that drawing's actual winning numbers."
    )
    st.caption(
        f"The replay then advances through {len(draws) - training_count:,} target drawings. "
        "Each one gets newly generated tickets using only results known before that drawing."
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
        st.session_state["backtest_result"] = result
        st.session_state["backtest_result_game"] = game.value
        st.session_state["backtest_result_config"] = {
            "strategy": backtest_strategy_slug,
            "start": test_from.isoformat(),
            "tickets_per_draw": tickets_per_draw,
            "simulations": simulations,
        }
        st.session_state[f"backtest_inspect_target_{game.value}"] = (
            result.draw_results[0].target_date
        )

    result = st.session_state.get("backtest_result")
    if st.session_state.get("backtest_result_game") != game.value:
        result = None
    if result is not None:
        current_config = {
            "strategy": backtest_strategy_slug,
            "start": test_from.isoformat(),
            "tickets_per_draw": tickets_per_draw,
            "simulations": simulations,
        }
        if st.session_state.get("backtest_result_config") != current_config:
            st.warning(
                "The controls above have changed. The results below are from the last completed "
                "replay; run the backtest again to apply the new settings."
            )
        st.caption(
            f"Last completed replay: {result.strategy} · {result.tickets_per_draw} tickets × "
            f"{result.simulations} portfolios per target drawing."
        )
        st.divider()
        st.subheader("Inspect a target drawing")
        st.caption(
            "Choose a drawing to see exactly what the algorithm knew, what it generated, and "
            "how those tickets compared with the real result."
        )
        target_options = [draw_result.target_date for draw_result in result.draw_results]
        inspect_key = f"backtest_inspect_target_{game.value}"
        if st.session_state.get(inspect_key) not in target_options:
            st.session_state[inspect_key] = target_options[0]
        selected_target = st.selectbox(
            "Target drawing",
            options=target_options,
            format_func=format_backtest_date,
            key=inspect_key,
        )
        selected_draw = next(
            draw_result
            for draw_result in result.draw_results
            if draw_result.target_date == selected_target
        )
        actual_white = "  ".join(f"{number:02d}" for number in selected_draw.actual_white)
        st.markdown(f"#### Actual result — {format_backtest_date(selected_draw.target_date)}")
        st.markdown(f"### {actual_white}  ·  Special {selected_draw.actual_special:02d}")
        st.caption(
            f"Every ticket below was generated from {selected_draw.training_draws:,} drawings "
            f"available through {format_backtest_date(selected_draw.training_cutoff)}."
        )
        detail_columns = st.columns(4)
        detail_columns[0].metric(
            "Training cutoff", format_backtest_date(selected_draw.training_cutoff)
        )
        detail_columns[1].metric("Tickets tested", f"{selected_draw.tickets_evaluated:,}")
        detail_columns[2].metric(
            "Best white match", f"{selected_draw.best_white_matches} of {rules.white_count}"
        )
        detail_columns[3].metric(
            "Special-ball hits", f"{selected_draw.special_matches:,}"
        )
        count_column, ticket_result_column = st.columns([1, 2])
        with count_column:
            st.markdown("**All tickets for this drawing**")
            st.dataframe(
                draw_match_frame(selected_draw),
                hide_index=True,
                use_container_width=True,
            )
        with ticket_result_column:
            st.markdown("**Best generated tickets**")
            st.dataframe(
                top_ticket_frame(selected_draw),
                hide_index=True,
                use_container_width=True,
            )
            st.caption(
                f"Showing the best {len(selected_draw.top_tickets):,} of "
                f"{selected_draw.tickets_evaluated:,} tickets. The table at left counts them all."
            )

        st.divider()
        st.subheader("Overall results across the full replay")
        st.caption(
            f"Combined results from {format_backtest_date(result.draw_results[0].target_date)} "
            f"through {format_backtest_date(result.draw_results[-1].target_date)}."
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
        with st.expander("Advanced probability scoring"):
            st.caption(
                "Lower Brier scores are better. Compare the algorithm with the random baseline; "
                "small differences can still be ordinary noise."
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
