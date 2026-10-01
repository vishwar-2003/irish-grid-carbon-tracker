import { num } from "../format.js";

export default function ModelCard({ model, source }) {
  if (!model || model.mae == null) {
    return (
      <section className="panel model">
        <h2>Forecast model</h2>
        <p className="sub">Not enough history yet; using yesterday's pattern as the forecast.</p>
      </section>
    );
  }
  return (
    <section className="panel model" aria-labelledby="model-title">
      <h2 id="model-title">Forecast model</h2>
      <p>
        Gradient-boosted trees predict hourly carbon intensity from EirGrid's own wind and demand
        forecasts, time of day and yesterday's intensity, with quantile models for the likely range.
        Retrained every 6 hours on the last {num(model.training_hours / 24)} days.
      </p>
      <dl className="metrics">
        <div><dt>Error (MAE), last 72 h</dt><dd className="mono">{num(model.mae, 1)} g</dd></div>
        <div><dt>Baseline: same hour yesterday</dt><dd className="mono">{num(model.mae_baseline, 1)} g</dd></div>
        <div><dt>Improvement on baseline</dt><dd className="mono">{num(model.skill_vs_baseline_pct)}%</dd></div>
      </dl>
      {source === "demo" && (
        <p className="warn">These figures are from simulated data and say nothing about real accuracy.</p>
      )}
    </section>
  );
}
