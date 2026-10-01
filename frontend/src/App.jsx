import { useCallback, useEffect, useState } from "react";
import { fetchDashboard } from "./api.js";
import { IntensityChart, WindChart } from "./components/charts.jsx";
import ModelCard from "./components/ModelCard.jsx";
import NowPanel from "./components/NowPanel.jsx";
import Planner from "./components/Planner.jsx";
import { hhmm, toMs } from "./format.js";

const REFRESH_MS = 5 * 60 * 1000;
const REGION = { ROI: "Ireland", NI: "Northern Ireland", ALL: "All-island" };

export default function App() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    try {
      setData(await fetchDashboard());
      setError(null);
    } catch (e) {
      setError(e.message);
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, REFRESH_MS);
    return () => clearInterval(id);
  }, [load]);

  if (!data) {
    return (
      <main className="page">
        <Header />
        <p className="status">{error ? `Could not load grid data: ${error}` : "Loading grid data..."}</p>
      </main>
    );
  }

  const { meta, current, history, forecast, model, greenest_hours, appliances } = data;
  const dish = appliances.find((a) => a.appliance === "dishwasher");
  const now = toMs(current.time);

  return (
    <main className="page">
      <Header meta={meta} current={current} />
      {meta.note && <p className={`notice notice-${meta.source}`}>{meta.note}</p>}
      {error && <p className="notice">Refresh failed ({error}); showing the last data received.</p>}
      <NowPanel current={current} appliances={appliances} />
      <div className="grid">
        <div className="charts">
          <IntensityChart history={history} forecast={forecast} bestWindow={dish?.best} now={now} />
          <WindChart history={history} forecast={forecast} now={now} />
        </div>
        <Planner appliances={appliances} greenest={greenest_hours} />
      </div>
      <ModelCard model={model} source={meta.source} />
      <footer>
        <p>{meta.attribution}. Figures are indicative and for information only.</p>
        <p>Built with React, FastAPI and scikit-learn.</p>
      </footer>
    </main>
  );
}

function Header({ meta, current }) {
  return (
    <header className="header">
      <div>
        <h1>Irish Grid Carbon Tracker</h1>
        <p className="sub">How clean is the electricity on Ireland's grid right now, and when will it be cleanest?</p>
      </div>
      {meta && (
        <div className="status-pill">
          <span className={`live-dot ${meta.source}`} aria-hidden="true" />
          {meta.source === "live" ? "Live" : "Demo"} · {REGION[meta.region] || meta.region} · updated {hhmm(current.time)}
        </div>
      )}
    </header>
  );
}
