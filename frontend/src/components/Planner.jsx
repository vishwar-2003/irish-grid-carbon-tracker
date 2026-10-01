import { useState } from "react";
import { grams, hhmm, num, when } from "../format.js";

export default function Planner({ appliances, greenest }) {
  const [selected, setSelected] = useState("dishwasher");
  const rec = appliances.find((a) => a.appliance === selected) || appliances[0];
  if (!rec) return null;
  return (
    <section className="panel planner" aria-labelledby="planner-title">
      <h2 id="planner-title">When should I run it?</h2>
      <div className="chips" role="radiogroup" aria-label="Appliance">
        {appliances.map((a) => (
          <button key={a.appliance} role="radio" aria-checked={a.appliance === rec.appliance}
            className={a.appliance === rec.appliance ? "chip active" : "chip"}
            onClick={() => setSelected(a.appliance)}>
            {a.label}
          </button>
        ))}
      </div>

      <div className="advice">
        <div>
          <p className="eyebrow">Best start</p>
          <p className="advice-time mono">{hhmm(rec.best.start)}</p>
          <p className="sub">{when(rec.best.start)} to {hhmm(rec.best.end)}, avg {num(rec.best.avg_intensity)} gCO₂/kWh</p>
        </div>
        <ul className="compare" aria-label="CO2 per run">
          <li className="compare-head"><span>CO₂ per run</span></li>
          <li><span>Best time</span><strong className="mono">{grams(rec.co2_best_g)}</strong></li>
          <li><span>Start now</span><strong className="mono">{grams(rec.co2_now_g)}</strong></li>
          <li><span>Worst time</span><strong className="mono">{grams(rec.co2_worst_g)}</strong></li>
        </ul>
      </div>
      <p className="saving">
        {rec.run_now
          ? "Now is the cleanest time in the next 24 hours."
          : `Waiting saves about ${grams(rec.saving_vs_now_g)} CO₂ (${num(rec.saving_vs_now_pct)}%) compared with starting now.`}
        <span className="sub"> Based on about {num(rec.kwh, 1)} kWh over {rec.hours} h; your appliance may differ.</span>
      </p>

      <h3 className="greenest-title">Greenest hours in the next 24 h</h3>
      <ol className="greenest">
        {greenest.map((h) => (
          <li key={h.time}>
            <span className="mono">{hhmm(h.time)}</span>
            <span className="sub">{num(h.intensity)} g · wind {num(h.wind_share)}%</span>
          </li>
        ))}
      </ol>
    </section>
  );
}
