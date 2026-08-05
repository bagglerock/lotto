# Data sources and validation

Lotto Lab uses public datasets supplied by the New York State Gaming Commission through the Socrata Open Data API.

| Game | Dataset | API endpoint |
|---|---|---|
| Powerball | `d6yy-54nr` | `https://data.ny.gov/resource/d6yy-54nr.json` |
| Mega Millions | `5xaw-6ayf` | `https://data.ny.gov/resource/5xaw-6ayf.json` |

Powerball supplies its five white balls and Powerball in one `winning_numbers` field. Mega Millions supplies five `winning_numbers` and a separate `mega_ball` field. The client normalizes both shapes into the same `Draw` model.

## Ingestion rules

- The Socrata query filters at the effective date of the configured current rule era.
- Incremental synchronization requests only dates newer than the latest stored drawing.
- White balls must be unique, sorted, have the configured count, and remain inside the configured range.
- The special ball is validated against its separate range.
- A malformed upstream record rejects the synchronization with its drawing date instead of being silently ignored.
- Transient rate-limit and server errors are retried with short exponential backoff.
- SQLite upserts make synchronization repeatable.

## Rule changes

The data API does not act as the application's rules registry. Rule eras are explicitly configured in `domain.py`. If a game changes again, a new configuration must be introduced and its effective date independently verified before the application accepts the new rows.

The present application deliberately analyzes only:

- Powerball's 5/69 + 1/26 era beginning October 7, 2015.
- Mega Millions' 5/70 + 1/24 era beginning April 8, 2025.
