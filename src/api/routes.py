"""Read-only HTTP API over the ingested Garmin daily stats.

Serves rows from the ``daily_stats`` table (see src/db/model.py). Runs against
whatever ``DB_URL`` points at, so it works on local SQLite now and on a hosted
Postgres after migration with no code change.

Run locally (from the project root):
    .venv/bin/uvicorn src.api.routes:app --reload
Then open http://127.0.0.1:8000/stats for the dashboard, or /docs for the API.
"""

from datetime import date
from typing import Optional

import anthropic
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from src.coach.coach import get_coaching
from src.db.db import SessionLocal
from src.db.model import DailyStats

app = FastAPI(title="Garmin daily stats", version="0.1.0")


def get_db():
    """Yield a request-scoped SQLAlchemy session, closed when the request ends."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _serialize(row: DailyStats) -> dict:
    """Turn a DailyStats row into a JSON-friendly dict keyed by snake_case attrs."""
    return {attr: getattr(row, attr) for attr in DailyStats.__mapper__.columns.keys()}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/stats", response_class=HTMLResponse)
def stats_dashboard():
    """Single-page dashboard: charts of the recent daily stats.

    Pure HTML + Chart.js (from a CDN). It fetches /days and renders the charts
    in the browser, so there's no server-side rendering or extra dependency.
    """
    return _DASHBOARD_HTML


@app.get("/days")
def list_days(
    limit: Optional[int] = Query(None, ge=1, le=1000, description="Max rows to return."),
    db: Session = Depends(get_db),
) -> list[dict]:
    """All days, newest first. Pass ?limit=N to cap the result."""
    q = db.query(DailyStats).order_by(DailyStats.calendar_date.desc())
    if limit is not None:
        q = q.limit(limit)
    return [_serialize(r) for r in q]


@app.get("/days/latest")
def latest_day(db: Session = Depends(get_db)) -> dict:
    """The most recently ingested day."""
    row = db.query(DailyStats).order_by(DailyStats.calendar_date.desc()).first()
    if row is None:
        raise HTTPException(status_code=404, detail="No data ingested yet.")
    return _serialize(row)


@app.get("/days/{calendar_date}")
def get_day(calendar_date: date, db: Session = Depends(get_db)) -> dict:
    """Full stats for one day. 404 if that day hasn't been ingested."""
    row = db.get(DailyStats, calendar_date)
    if row is None:
        raise HTTPException(status_code=404, detail=f"No data for {calendar_date}.")
    return _serialize(row)


@app.get("/coach")
def coach(
    days: int = Query(14, ge=1, le=90, description="Days of history to analyze."),
    note: Optional[str] = Query(None, description="Optional message to the coach."),
    refresh: bool = Query(False, description="Bypass the cache and regenerate."),
) -> dict:
    """LLM coaching advice (workout / recovery / general) over recent stats.

    Calls Claude via ``src.coach.coach`` — needs ``ANTHROPIC_API_KEY`` set. The
    ``advice`` field is markdown; the dashboard renders it. Responses are cached
    until a new day is ingested; pass ``?refresh=true`` to force a new call.
    """
    try:
        result = get_coaching(days=days, extra_note=note, force=refresh)
    except RuntimeError as e:  # no data ingested yet
        raise HTTPException(status_code=404, detail=str(e))
    except anthropic.AuthenticationError:
        raise HTTPException(
            status_code=503,
            detail="Coach unavailable: ANTHROPIC_API_KEY is missing or invalid.",
        )
    except anthropic.APIError as e:  # upstream model/network error
        raise HTTPException(status_code=502, detail=f"Coach model error: {e}")
    except HTTPException:
        raise
    except Exception as e:  # never leak an opaque 500 — surface the cause
        raise HTTPException(status_code=500, detail=f"Coach failed: {e!r}")
    return {
        "advice": result.advice,
        "model": result.model,
        "days_analyzed": result.days_analyzed,
        "date_range": result.date_range,
        "generated_at": result.generated_at,
        "cached": result.cached,
    }


# --- Dashboard page --------------------------------------------------------
# Self-contained: loads Chart.js from a CDN, fetches /days, draws the charts.
_DASHBOARD_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Garmin daily stats</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
  <script src="https://cdn.jsdelivr.net/npm/marked@12/marked.min.js"></script>
  <style>
    :root { color-scheme: light dark; }
    body { font-family: -apple-system, system-ui, sans-serif; margin: 0; padding: 24px;
           background: #0f1115; color: #e6e6e6; }
    h1 { font-size: 20px; margin: 0 0 4px; }
    .sub { color: #8a90a2; font-size: 13px; margin-bottom: 20px; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
            gap: 16px; }
    .card { background: #171a21; border: 1px solid #232838; border-radius: 12px;
            padding: 16px; }
    .card h2 { font-size: 14px; margin: 0 0 12px; color: #c8cdda; font-weight: 600; }
    canvas { width: 100% !important; height: 260px !important; }
    .empty { color: #8a90a2; padding: 40px; text-align: center; }
    /* Coach panel */
    #coach-card { margin-bottom: 16px; }
    .coach-head { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
    .coach-head h2 { margin: 0; }
    #coach-refresh { background: #232838; color: #c8cdda; border: 1px solid #2f3650;
                     border-radius: 8px; padding: 5px 12px; font-size: 12px; cursor: pointer; }
    #coach-refresh:hover { background: #2b3147; }
    #coach-refresh:disabled { opacity: .5; cursor: default; }
    #coach-meta { color: #8a90a2; font-size: 12px; margin-left: auto; }
    #coach-body { line-height: 1.5; font-size: 14px; color: #dfe3ee; }
    #coach-body h2 { font-size: 14px; color: #4f8cff; margin: 16px 0 6px; }
    #coach-body h2:first-child { margin-top: 4px; }
    #coach-body p { margin: 6px 0; }
    #coach-body ul { margin: 6px 0; padding-left: 20px; }
    .coach-err { color: #ff6b6b; }
  </style>
</head>
<body>
  <h1>Garmin daily stats</h1>
  <div class="sub" id="sub">Loading…</div>

  <div class="card" id="coach-card">
    <div class="coach-head">
      <h2>🏋️ Coach</h2>
      <button id="coach-refresh">Ask the coach</button>
      <span id="coach-meta"></span>
    </div>
    <div id="coach-body" class="empty">Click “Ask the coach” for advice on today.</div>
  </div>

  <div class="grid" id="grid"></div>

  <script>
  const coachBody = document.getElementById("coach-body");
  const coachMeta = document.getElementById("coach-meta");
  const coachBtn = document.getElementById("coach-refresh");

  async function loadCoach() {
    coachBtn.disabled = true;
    coachBody.className = "";
    coachBody.textContent = "Thinking through your recent data…";
    coachMeta.textContent = "";
    try {
      const res = await fetch("/coach");
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || res.statusText);
      coachBody.innerHTML = marked.parse(data.advice);
      coachMeta.textContent =
        `${data.model} · ${data.days_analyzed} days (${data.date_range})`
        + (data.cached ? " · cached" : "");
    } catch (e) {
      coachBody.className = "coach-err";
      coachBody.textContent = "Coach failed: " + e.message;
    } finally {
      coachBtn.disabled = false;
    }
  }
  coachBtn.addEventListener("click", loadCoach);
  </script>

  <script>
  const HOUR = 3600;
  const palette = {
    blue: "#4f8cff", green: "#3ecf8e", amber: "#f5a623",
    red: "#ff6b6b", purple: "#b07cff", gray: "#8a90a2",
  };

  function card(title) {
    const c = document.createElement("div");
    c.className = "card";
    c.innerHTML = `<h2>${title}</h2><canvas></canvas>`;
    document.getElementById("grid").appendChild(c);
    return c.querySelector("canvas");
  }

  const baseOpts = {
    responsive: true, maintainAspectRatio: false,
    plugins: { legend: { labels: { color: "#c8cdda", boxWidth: 12 } } },
    scales: {
      x: { ticks: { color: "#8a90a2" }, grid: { color: "#232838" } },
      y: { ticks: { color: "#8a90a2" }, grid: { color: "#232838" }, beginAtZero: true },
    },
  };

  function lineChart(canvas, labels, datasets) {
    new Chart(canvas, { type: "line",
      data: { labels, datasets: datasets.map(d => ({ ...d, tension: 0.3, spanGaps: true })) },
      options: baseOpts });
  }
  function barChart(canvas, labels, datasets, stacked=false) {
    const opts = JSON.parse(JSON.stringify(baseOpts));
    if (stacked) { opts.scales.x.stacked = true; opts.scales.y.stacked = true; }
    new Chart(canvas, { type: "bar", data: { labels, datasets }, options: opts });
  }

  async function main() {
    const rows = await (await fetch("/days")).json();
    rows.reverse();  // /days is newest-first; charts read left-to-right in time

    if (!rows.length) {
      document.getElementById("sub").textContent = "";
      document.getElementById("grid").innerHTML =
        '<div class="empty">No data ingested yet.</div>';
      return;
    }

    const labels = rows.map(r => r.calendar_date);
    const col = (k) => rows.map(r => r[k]);
    document.getElementById("sub").textContent =
      `${rows.length} day(s): ${labels[0]} → ${labels[labels.length - 1]}`;

    barChart(card("Steps"), labels, [
      { label: "Steps", data: col("total_steps"), backgroundColor: palette.blue },
    ]);

    lineChart(card("Resting heart rate (bpm)"), labels, [
      { label: "Resting HR", data: col("resting_heart_rate"), borderColor: palette.red },
    ]);

    barChart(card("Sleep score"), labels, [
      { label: "Sleep score", data: col("sleep_score_overall_value"),
        backgroundColor: palette.purple },
    ]);

    barChart(card("Sleep stages (hours)"), labels, [
      { label: "Deep",  data: col("sleep_deep_sleep_seconds").map(v => v/HOUR),  backgroundColor: palette.blue },
      { label: "Light", data: col("sleep_light_sleep_seconds").map(v => v/HOUR), backgroundColor: palette.green },
      { label: "REM",   data: col("sleep_rem_sleep_seconds").map(v => v/HOUR),   backgroundColor: palette.purple },
      { label: "Awake", data: col("sleep_awake_sleep_seconds").map(v => v/HOUR), backgroundColor: palette.amber },
    ], true);

    lineChart(card("Stress"), labels, [
      { label: "Avg", data: col("average_stress_level"), borderColor: palette.amber },
      { label: "Max", data: col("max_stress_level"), borderColor: palette.red },
    ]);

    lineChart(card("Body battery"), labels, [
      { label: "High", data: col("body_battery_highest_value"), borderColor: palette.green },
      { label: "Low",  data: col("body_battery_lowest_value"),  borderColor: palette.gray },
    ]);

    barChart(card("Calories"), labels, [
      { label: "Active", data: col("active_kilocalories"), backgroundColor: palette.amber },
      { label: "BMR",    data: col("bmr_kilocalories"),    backgroundColor: palette.gray },
    ], true);

    lineChart(card("Intensity minutes"), labels, [
      { label: "Moderate", data: col("moderate_intensity_minutes"), borderColor: palette.green },
      { label: "Vigorous", data: col("vigorous_intensity_minutes"), borderColor: palette.red },
    ]);
  }

  main().catch(e => {
    document.getElementById("sub").textContent = "Failed to load: " + e;
  });
  </script>
</body>
</html>
"""
