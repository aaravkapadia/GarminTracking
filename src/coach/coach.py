"""LLM 'online coach' over the ingested Garmin daily stats.

Reads recent rows from the ``daily_stats`` table, hands Claude a compact digest
of the numbers, and asks it to act like a personal coach — reading the trends
and returning workout / recovery / general guidance as markdown.

The model is Claude Opus 4.8 via the Anthropic SDK. Auth comes from
``ANTHROPIC_API_KEY`` (put it in ``.env`` next to the Garmin credentials); the
SDK picks it up from the environment.

Programmatic use:
    from src.coach.coach import get_coaching
    print(get_coaching(days=14).advice)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from datetime import datetime, timezone

import anthropic

from src.db.db import SessionLocal
from src.db.model import DailyStats

MODEL = "claude-opus-4-8"

# The metrics a coach actually reasons about, in the order they appear in the
# per-day digest line. (attribute, label, formatter).
_FIELDS = [
    ("total_steps", "steps", lambda v: f"{int(v)}"),
    ("resting_heart_rate", "rhr", lambda v: f"{int(v)}bpm"),
    ("sleep_score_overall_value", "sleep_score", lambda v: f"{int(v)}"),
    ("sleep_sleep_time_seconds", "sleep", lambda v: f"{v / 3600:.1f}h"),
    ("sleep_deep_sleep_seconds", "deep", lambda v: f"{v / 3600:.1f}h"),
    ("sleep_rem_sleep_seconds", "rem", lambda v: f"{v / 3600:.1f}h"),
    ("sleep_avg_overnight_hrv", "hrv", lambda v: f"{v:.0f}ms"),
    ("sleep_hrv_status", "hrv_status", str),
    ("average_stress_level", "stress_avg", lambda v: f"{int(v)}"),
    ("body_battery_highest_value", "bb_high", lambda v: f"{int(v)}"),
    ("body_battery_lowest_value", "bb_low", lambda v: f"{int(v)}"),
    ("moderate_intensity_minutes", "mod_min", lambda v: f"{int(v)}"),
    ("vigorous_intensity_minutes", "vig_min", lambda v: f"{int(v)}"),
    ("active_kilocalories", "active_kcal", lambda v: f"{int(v)}"),
]

_SYSTEM = """\
You are an experienced endurance and strength coach reviewing a client's \
wearable data (from a Garmin watch). You get a digest of the last few days of \
daily metrics and act as their online coach.

Read the trends, not just single days. Pay attention to recovery signals \
(resting heart rate, HRV and its status, sleep duration and quality, body \
battery, stress) against training load (intensity minutes, steps, active \
calories). Call out anything notable: an elevated resting HR, dropping HRV, \
poor sleep, a hard-training streak with no easy days, or a well-recovered day \
that's a good chance to push.

Respond in concise markdown with exactly these four sections, in this order:

## Readiness
One short line: a readiness read for today (e.g. "Recover", "Easy", "Train", \
"Push") plus one sentence of why, grounded in the numbers.

## Workout
What to do today and why, referencing the data. Be specific and actionable.

## Recovery
Concrete recovery guidance (sleep, stress, nutrition, mobility) tied to what \
the data shows.

## General
One or two broader observations about the trend over these days.

Ground every claim in the numbers you were given — cite the metric and its \
value or trend. Keep it tight and practical; no preamble, no medical \
disclaimers. You are a coach, not a doctor."""


@dataclass
class Coaching:
    """Result of a coaching call."""

    advice: str  # markdown
    model: str
    days_analyzed: int
    date_range: str  # "2026-06-23 → 2026-07-06", or "" when no data
    generated_at: str  # ISO-8601 UTC
    cached: bool = False  # True when served from the in-memory cache


# In-memory cache. Keyed by (days, note, latest_ingested_date) so advice is
# reused until a new day is ingested (or the window / note changes). Process-
# local — clears on restart, which is fine for a single-user app.
_CACHE: dict[tuple, Coaching] = {}


def _digest(rows: list[DailyStats]) -> str:
    """Render rows (chronological, oldest first) as one compact line per day.

    Days with no populated metrics are skipped so the model isn't fed noise.
    """
    lines = []
    for r in rows:
        parts = []
        for attr, label, fmt in _FIELDS:
            value = getattr(r, attr, None)
            if value is not None and value != "":
                parts.append(f"{label}={fmt(value)}")
        if parts:  # skip days with nothing recorded
            lines.append(f"{r.calendar_date}: " + ", ".join(parts))
    return "\n".join(lines)


def get_coaching(
    days: int = 14, extra_note: str | None = None, force: bool = False
) -> Coaching:
    """Analyze the most recent ``days`` of stats and return coaching advice.

    ``extra_note`` is an optional free-text message from the user (e.g. "I have
    a race Saturday") that gets appended to the prompt.

    Results are cached in-process keyed by ``(days, note, latest ingested day)``,
    so repeat calls don't re-hit the model until new data lands. Pass
    ``force=True`` to bypass the cache and regenerate.

    Raises ``RuntimeError`` if there is no data yet, or the SDK's
    ``AuthenticationError`` if ``ANTHROPIC_API_KEY`` is missing/invalid.
    """
    with SessionLocal() as session:
        rows = (
            session.query(DailyStats)
            .order_by(DailyStats.calendar_date.desc())
            .limit(days)
            .all()
        )

    if not rows:
        raise RuntimeError("No Garmin data ingested yet — nothing to coach on.")

    latest_date = rows[0].calendar_date  # newest ingested day (rows are desc)
    cache_key = (days, extra_note, latest_date)

    # Drop entries from older ingest days so the cache doesn't grow unbounded.
    for key in [k for k in _CACHE if k[2] != latest_date]:
        del _CACHE[key]

    if not force and cache_key in _CACHE:
        return replace(_CACHE[cache_key], cached=True)

    rows.reverse()  # chronological: oldest first so trends read left-to-right
    digest = _digest(rows)

    user_content = (
        f"Here is the last {len(rows)} day(s) of my Garmin daily stats, "
        f"oldest first:\n\n{digest}\n\n"
        "Coach me for today based on this."
    )
    if extra_note:
        user_content += f"\n\nAlso keep this in mind: {extra_note}"

    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the env
    response = client.messages.create(
        model=MODEL,
        max_tokens=3000,
        system=_SYSTEM,
        thinking={"type": "adaptive"},
        output_config={"effort": "medium"},
        messages=[{"role": "user", "content": user_content}],
    )

    advice = "".join(b.text for b in response.content if b.type == "text").strip()

    result = Coaching(
        advice=advice,
        model=response.model,
        days_analyzed=len(rows),
        date_range=f"{rows[0].calendar_date} → {rows[-1].calendar_date}",
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    _CACHE[cache_key] = result
    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Garmin LLM coach")
    parser.add_argument("--days", type=int, default=14, help="Days of data to analyze.")
    parser.add_argument("--note", help="Optional note to pass to the coach.")
    args = parser.parse_args()

    if not os.getenv("ANTHROPIC_API_KEY"):
        raise SystemExit("Set ANTHROPIC_API_KEY (in .env) to run the coach.")

    result = get_coaching(days=args.days, extra_note=args.note)
    print(f"# Coach ({result.model}, {result.date_range})\n")
    print(result.advice)
