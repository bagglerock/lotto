# Lotto Lab

Lotto Lab is a local research application for exploring Powerball and Mega Millions number-selection strategies. It downloads official drawing results, generates tickets with transparent algorithms, and measures those algorithms using walk-forward backtesting.

It does **not** claim that a random lottery can be reliably predicted. Its job is to distinguish interesting-looking patterns from strategies that actually survive unseen historical drawings.

## What is included

- Current-format Powerball results from October 7, 2015 onward
- Current-format Mega Millions results from April 8, 2025 onward
- Official New York State Gaming Commission open-data feeds
- Pure Random, Bayesian Hot, Bayesian Cold, Hot/Cold Mix, Recent Trend, Overdue, and Combined strategies
- Seeded, reproducible ticket generation
- Strict walk-forward backtesting with no future-data leakage
- Random-baseline comparisons, Brier scores, and bootstrap intervals
- Immutable, versioned predictions that can be locked before a future drawing
- A command-line interface and a local Streamlit interface backed by the same engine
- SQLite storage that remains on the local machine

## Setup

Python 3.11 or newer is required.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
lotto-lab sync
lotto-lab ui
```

The UI opens locally at `http://localhost:8501`. Streamlit runs on the laptop; it is not necessary to deploy the application to use it.

The NY Open Data SODA 2.1 endpoints work without credentials for light use. A free Socrata app token can optionally be supplied for identified requests:

```bash
export SOCRATA_APP_TOKEN="your-token"
```

## CLI examples

```bash
# Download both games and show local status
lotto-lab sync
lotto-lab status

# Generate deterministic tickets
lotto-lab generate --game powerball --strategy bayesian-hot --tickets 10 --seed 42

# Generate and permanently record a prediction made before a drawing
lotto-lab generate --game powerball --strategy combined --tickets 10 --seed 42 --lock

# Test one strategy or compare every strategy
lotto-lab backtest --game powerball --strategy recent-trend --test-from 2023-01-01 --simulations 50
lotto-lab compare --game powerball --simulations 20
```

Use `lotto-lab --help` or `lotto-lab <command> --help` for every option.

## Current-format isolation

The upstream datasets contain older rule eras. Lotto Lab deliberately filters them at ingestion and validates every draw against the configured current rules:

| Game | Effective date | White balls | Special ball |
|---|---:|---:|---:|
| Powerball | 2015-10-07 | 5 from 1–69 | 1 from 1–26 |
| Mega Millions | 2025-04-08 | 5 from 1–70 | 1 from 1–24 |

Mega Millions has a much younger current-format dataset. The UI displays a persistent low-confidence notice instead of presenting its early frequency differences as strong evidence.

## Development

```bash
pytest
ruff check .
```

More detail is available in:

- [Architecture](docs/ARCHITECTURE.md)
- [Statistical methods](docs/STATISTICAL_METHODS.md)
- [Data sources and validation](docs/DATA_SOURCES.md)

## Responsible use

Every valid combination has the same theoretical jackpot probability in a fair drawing. Backtest results can arise from chance, and simulated performance does not guarantee future performance. Treat lottery spending as entertainment and set a fixed budget independent of anything this application displays.
