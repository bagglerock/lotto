# Lotto Lab

Lotto Lab is a local dashboard for exploring Powerball and Mega Millions drawing history. It can generate tickets with several transparent strategies—hot, cold, mixed, recent-trend, overdue, combined, and random—and test them against past drawings without using future data.

This is a statistics playground, **not a winning-number predictor**. In a fair drawing, every valid combination has the same chance, and patterns in past results do not change the odds of the next draw.

## Run it

Python 3.11 or newer is required. Python 3.12 is recommended.

```bash
cd lotto
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'

lotto-lab sync
lotto-lab ui
```

Open [http://localhost:8501](http://localhost:8501). Stop the server with `Ctrl+C`.

On later runs:

```bash
cd lotto
source .venv/bin/activate
lotto-lab sync   # fetch any newer drawings
lotto-lab ui
```

The app stores its data locally in SQLite. The official NY Open Data feeds do not require an API key for normal use.

## Current drawing formats

| Game | Results used | Format |
|---|---|---|
| Powerball | October 7, 2015 onward | 5 from 1–69 + 1 from 1–26 |
| Mega Millions | April 8, 2025 onward | 5 from 1–70 + 1 from 1–24 |

Mega Millions has far fewer current-format drawings, so the dashboard marks conclusions from that dataset as lower confidence.

## Troubleshooting

### `requires a different Python`

The virtual environment was created with Python 3.9 or 3.10. Recreate it with Python 3.12:

```bash
deactivate 2>/dev/null || true
rm -rf .venv
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
```

### `command not found: lotto-lab`

The environment is inactive or installation did not finish:

```bash
source .venv/bin/activate
python -m pip install -e '.[dev]'
```

### Browser shows `Connection failed with status 500`

Pull the latest code and reinstall the dependencies:

```bash
git pull
source .venv/bin/activate
python -m pip install -e '.[dev]'
lotto-lab ui
```

For the older Streamlit/Starlette conflict specifically, this temporary repair also works:

```bash
python -m pip install 'starlette<1'
lotto-lab ui
```

## Optional CLI

```bash
lotto-lab status
lotto-lab generate --game powerball --strategy combined --tickets 10 --seed 42
lotto-lab compare --game powerball --simulations 20
lotto-lab --help
```

## Development

```bash
pytest
ruff check .
```

Technical details are in [Architecture](docs/ARCHITECTURE.md), [Statistical methods](docs/STATISTICAL_METHODS.md), and [Data sources](docs/DATA_SOURCES.md).

Play for entertainment, not as an investment, and use a fixed budget.
