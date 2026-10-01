# Irish Grid Carbon Tracker

How clean is the electricity on Ireland's grid right now, and when will it be cleanest?

**Live demo:** https://irish-grid-carbon-tracker.onrender.com

![Dashboard](docs/screenshot.png)

The app pulls EirGrid's public system data, shows live carbon intensity and the share of demand met by wind, forecasts carbon intensity for the next 24 hours, and recommends the greenest times to run household appliances.

## Features

- **Live grid status** - carbon intensity (gCO₂/kWh), wind and solar share of demand, and the 24-hour range, refreshed every 5 minutes.
- **24-hour forecast** - hourly carbon intensity with a likely range (p10-p90), from a gradient-boosted model.
- **Appliance planner** - the best start time for a dishwasher, washing machine, tumble dryer, EV charge or immersion heater, with the CO₂ saved compared with starting now.
- **Greenest hours** - the four lowest-carbon hours in the next day.
- **Model transparency** - forecast error on recent data, compared with a "same hour yesterday" baseline, shown in the app.

**Stack:** React, Vite, Recharts · Python, FastAPI, pandas, scikit-learn · Docker, GitHub Actions, Render

## Architecture

```
EirGrid Smart Grid Dashboard  -->  FastAPI backend          -->  React dashboard
15-min CO2 intensity, wind,        - data fetch and caching      - live status tiles
solar, demand, and EirGrid's       - feature engineering         - 48 h intensity chart
wind and demand forecasts          - forecast model              - wind share chart
                                   - window optimiser            - appliance planner
```

**Data pipeline** (`backend/app/eirgrid.py`, `backend/app/data.py`)
- Requests each data series per day, in parallel, with retries; a failed day is skipped rather than failing the whole load.
- Parses EirGrid's 15-minute readings into a time-zone-aware pandas frame and aggregates to hourly.
- Caches older history for 6 hours and the recent window for 10 minutes to limit load on EirGrid.
- Falls back to the last good live data if EirGrid stops responding, and labels the source on screen.

**Forecast model** (`backend/app/forecast.py`)

Carbon intensity on the Irish grid moves mostly with how much demand is met by wind, so the model predicts hourly intensity from:
- forecast wind share (EirGrid wind forecast ÷ demand forecast)
- forecast wind and demand in MW
- hour of day (cyclical encoding), day of week, weekend flag
- intensity at the same hour on the previous day

It uses `HistGradientBoostingRegressor` with absolute-error loss for the central forecast and two quantile models for the p10-p90 range. Training uses EirGrid's *forecast* wind rather than the actual, so inputs match between training and prediction. The model retrains every 6 hours on the last 21 days and is evaluated on the most recent 72 hours, held out in time order, against a seasonal-naive baseline.

**Recommendations** (`backend/app/recommend.py`)

For each appliance (typical energy per cycle and run time), every contiguous window in the forecast is scored and the lowest-average window is chosen. CO₂ per run = kWh × average intensity.

## Evaluation

`backend/evaluate.py` runs a rolling-origin backtest: for each of the last N days, it trains only on earlier data, forecasts that day, and compares the forecast with what was measured.

```bash
cd backend
python evaluate.py --days 35 --folds 7
```

It reports mean absolute error, improvement over the seasonal-naive baseline, MAPE, and how close the recommended 2-hour window was to the truly greenest one.

## Run locally

Requires Python 3.11+ and Node 18+.

```bash
# Backend
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000

# Frontend (second terminal)
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. Interactive API docs are at http://localhost:8000/docs.

Run the tests with `cd backend && pytest -q`. To check connectivity to EirGrid, run `python check_eirgrid.py`.

## API

| Endpoint | Returns |
|---|---|
| `GET /api/dashboard` | All dashboard data in one call |
| `GET /api/current` | Latest intensity, wind share, demand |
| `GET /api/history?hours=24` | Hourly measured intensity and wind share |
| `GET /api/forecast` | 24 h forecast with p10/p90 and model metrics |
| `GET /api/recommendations?appliance=ev_charge` | Best window and CO₂ saving |
| `GET /api/appliances` | Appliance assumptions |

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `DATA_MODE` | `auto` | `auto` (live with fallback), `live`, or `demo` (simulated data, no network) |
| `GRID_REGION` | `ROI` | `ROI`, `NI` or `ALL` (all-island) |
| `TRAINING_DAYS` | `21` | Days of history used for training |

## Project structure

```
backend/
  app/eirgrid.py      EirGrid client and parser
  app/data.py         caching and fallback
  app/forecast.py     features, training, 24 h prediction
  app/recommend.py    appliance windows and greenest hours
  app/main.py         FastAPI routes; serves the built React app
  evaluate.py         rolling-origin backtest
  tests/              pytest suite
frontend/
  src/App.jsx         layout and data loading
  src/components/     status panel, charts, planner, model card
Dockerfile            multi-stage build (Node build + Python runtime)
render.yaml           Render deployment
.github/workflows/    CI: tests and front-end build
```

## Deployment

Deployed on Render as a single Docker service defined in `render.yaml`. Every push to `main` runs CI and redeploys.

## Limitations

- EirGrid's dashboard endpoint is public but undocumented, so its format can change; all parsing is isolated in `eirgrid.py`.
- When EirGrid publishes CO₂ emissions without the intensity figure, intensity is derived as emissions ÷ demand, a close approximation.
- Carbon intensity is the grid average, not the marginal emissions of switching a device on.
- Appliance energy figures are typical values; real use varies by model and programme.

## Data

Grid data from [EirGrid Smart Grid Dashboard](https://www.smartgriddashboard.com). This project is not affiliated with EirGrid.

## Author

Vishwa Ravikumar · [LinkedIn](https://www.linkedin.com/in/vishwa2003/) · [GitHub](https://github.com/vishwar-2003)
