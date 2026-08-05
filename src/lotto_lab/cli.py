from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np

from lotto_lab.backtest import run_backtest
from lotto_lab.data import Database, DataSourceError, NyOpenDataClient, sync_game
from lotto_lab.domain import GAME_RULES, Game, parse_game
from lotto_lab.strategies import STRATEGIES, get_strategy


def _game_argument(value: str) -> Game:
    try:
        return parse_game(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _database(value: str | None) -> Database:
    return Database(value) if value else Database()


def _ticket_text(white: tuple[int, ...], special: int) -> str:
    return f"{' '.join(f'{value:02d}' for value in white)}  |  {special:02d}"


def command_sync(args: argparse.Namespace) -> int:
    database = _database(args.database)
    client = NyOpenDataClient()
    games = list(Game) if args.game == "all" else [_game_argument(args.game)]
    failed = False
    for game in games:
        try:
            fetched, changed = sync_game(database, client, game)
            total = len(database.list_draws(game))
            print(
                f"{game.display_name}: fetched {fetched}, "
                f"stored/updated {changed}, total {total}"
            )
        except DataSourceError as exc:
            failed = True
            print(f"{game.display_name}: {exc}", file=sys.stderr)
    return int(failed)


def command_status(args: argparse.Namespace) -> int:
    database = _database(args.database)
    for game in Game:
        draws = database.list_draws(game)
        latest = draws[-1].draw_date.isoformat() if draws else "never"
        print(f"{game.display_name}: {len(draws)} current-era drawings; latest {latest}")
    return 0


def command_generate(args: argparse.Namespace) -> int:
    game = args.game
    rules = GAME_RULES[game]
    database = _database(args.database)
    draws = database.list_draws(game)
    if not draws:
        raise SystemExit(f"No {game.display_name} data. Run 'lotto-lab sync' first.")
    strategy = get_strategy(args.strategy)
    rng = np.random.default_rng(args.seed)
    tickets = strategy.generate(draws, rules, args.tickets, rng)
    print(f"{game.display_name} · {strategy.name} · data through {draws[-1].draw_date}")
    for index, ticket in enumerate(tickets, 1):
        print(f"{index:>2}. {_ticket_text(ticket.white, ticket.special)}")

    if args.lock:
        earliest = max(date.today(), draws[-1].draw_date + timedelta(days=1))
        target = (
            date.fromisoformat(args.target_date)
            if args.target_date
            else rules.draw_date_on_or_after(earliest)
        )
        prediction_id = database.save_prediction(
            game=game,
            target_date=target,
            strategy=strategy.name,
            strategy_version=f"{strategy.slug}:{strategy.version}",
            data_cutoff=draws[-1].draw_date,
            seed=args.seed,
            parameters={"tickets": args.tickets},
            tickets=tickets,
        )
        print(f"Locked prediction #{prediction_id} for {target}")
    return 0


def command_backtest(args: argparse.Namespace) -> int:
    game = args.game
    database = _database(args.database)
    draws = database.list_draws(game)
    strategy = get_strategy(args.strategy)
    result = run_backtest(
        draws,
        GAME_RULES[game],
        strategy,
        min_training_draws=args.min_training,
        tickets_per_draw=args.tickets_per_draw,
        simulations=args.simulations,
        seed=args.seed,
        test_from=date.fromisoformat(args.test_from) if args.test_from else None,
    )
    if args.json:
        print(json.dumps(result.as_dict(), indent=2))
        return 0
    print(f"{game.display_name} · {result.strategy} walk-forward backtest")
    print(f"Draws tested:            {result.draws_tested:,}")
    print(f"Virtual tickets:         {result.tickets_evaluated:,}")
    print(f"Average white matches:   {result.average_white_matches:.5f}")
    print(f"Random expectation:      {result.random_expected_white_matches:.5f}")
    print(f"White-match lift:        {result.white_match_lift_percent:+.3f}%")
    print(f"Special-ball match rate: {result.special_match_rate:.5%}")
    print(f"Special-ball lift:       {result.special_match_lift_percent:+.3f}%")
    print(f"White Brier score:       {result.white_brier_score:.7f}")
    print(f"Random Brier score:      {result.random_white_brier_score:.7f}")
    print(
        f"95% lift interval:       {result.white_lift_ci_95[0]:+.5f} "
        f"to {result.white_lift_ci_95[1]:+.5f}"
    )
    return 0


def command_compare(args: argparse.Namespace) -> int:
    game = args.game
    database = _database(args.database)
    draws = database.list_draws(game)
    results = []
    for strategy in STRATEGIES.values():
        result = run_backtest(
            draws,
            GAME_RULES[game],
            strategy,
            min_training_draws=args.min_training,
            tickets_per_draw=args.tickets_per_draw,
            simulations=args.simulations,
            seed=args.seed,
            test_from=date.fromisoformat(args.test_from) if args.test_from else None,
        )
        results.append(result)
    print("Strategy                  White lift   Special lift   White Brier")
    print("------------------------  -----------  -------------  -----------")
    for result in sorted(results, key=lambda item: item.white_brier_score):
        print(
            f"{result.strategy:<24}  {result.white_match_lift_percent:>+10.3f}%"
            f"  {result.special_match_lift_percent:>+12.3f}%"
            f"  {result.white_brier_score:>11.7f}"
        )
    return 0


def command_ui(args: argparse.Namespace) -> int:
    app = Path(__file__).parent / "ui" / "app.py"
    command = [sys.executable, "-m", "streamlit", "run", str(app)]
    if args.database:
        command.extend(["--", "--database", args.database])
    return subprocess.call(command)  # noqa: S603


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lotto-lab",
        description="Transparent lottery strategies with walk-forward backtesting.",
    )
    parser.add_argument("--database", help="Override the SQLite database path")
    subparsers = parser.add_subparsers(dest="command", required=True)

    sync_parser = subparsers.add_parser("sync", help="Download current-era drawing results")
    sync_parser.add_argument(
        "--game", default="all", choices=["all", *[game.value for game in Game]]
    )
    sync_parser.set_defaults(handler=command_sync)

    status_parser = subparsers.add_parser("status", help="Show locally stored data")
    status_parser.set_defaults(handler=command_status)

    generate_parser = subparsers.add_parser("generate", help="Generate strategy-weighted tickets")
    generate_parser.add_argument("--game", type=_game_argument, default=Game.POWERBALL)
    generate_parser.add_argument("--strategy", choices=STRATEGIES, default="random")
    generate_parser.add_argument("--tickets", type=int, default=5)
    generate_parser.add_argument("--seed", type=int, default=20260805)
    generate_parser.add_argument("--lock", action="store_true", help="Save an immutable prediction")
    generate_parser.add_argument("--target-date", help="Target date in YYYY-MM-DD format")
    generate_parser.set_defaults(handler=command_generate)

    for name, handler in (("backtest", command_backtest), ("compare", command_compare)):
        backtest_parser = subparsers.add_parser(
            name, help=f"{name.title()} strategies historically"
        )
        backtest_parser.add_argument("--game", type=_game_argument, default=Game.POWERBALL)
        if name == "backtest":
            backtest_parser.add_argument("--strategy", choices=STRATEGIES, default="random")
            backtest_parser.add_argument("--json", action="store_true")
        backtest_parser.add_argument("--min-training", type=int, default=100)
        backtest_parser.add_argument("--tickets-per-draw", type=int, default=10)
        backtest_parser.add_argument("--simulations", type=int, default=20)
        backtest_parser.add_argument("--seed", type=int, default=20260805)
        backtest_parser.add_argument(
            "--test-from", help="First unseen drawing to evaluate, in YYYY-MM-DD format"
        )
        backtest_parser.set_defaults(handler=handler)

    ui_parser = subparsers.add_parser("ui", help="Open the local Streamlit interface")
    ui_parser.set_defaults(handler=command_ui)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        raise SystemExit(args.handler(args))
    except (OSError, ValueError) as exc:
        parser.exit(2, f"error: {exc}\n")
