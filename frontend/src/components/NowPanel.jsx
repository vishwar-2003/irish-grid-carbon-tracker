import { BAND_LABEL, num, when } from "../format.js";

function verdict(current, appliances) {
  const dish = appliances.find((a) => a.appliance === "dishwasher");
  if (!dish) return null;
  if (dish.run_now || dish.saving_vs_now_pct < 5) {
    return { tone: "go", text: "Now is a good time to run appliances." };
  }
  return {
    tone: "wait",
    text: `If you can wait, ${when(dish.best.start)} is about ${num(dish.saving_vs_now_pct)}% cleaner than now.`,
  };
}

export default function NowPanel({ current, appliances }) {
  const v = verdict(current, appliances);
  return (
    <section className="now" aria-labelledby="now-title">
      <div className="now-main">
        <h2 id="now-title" className="eyebrow">Carbon intensity now</h2>
        <p className="hero-number">
          <span className="mono">{num(current.intensity)}</span>
          <span className="unit">gCO₂/kWh</span>
        </p>
        <p className={`band band-${current.band}`}>
          <span className="dot" aria-hidden="true" />
          {BAND_LABEL[current.band]}
        </p>
        {v && <p className={`verdict verdict-${v.tone}`}>{v.text}</p>}
      </div>
      <dl className="tiles">
        <div className="tile">
          <dt>Wind share</dt>
          <dd className="mono">{num(current.wind_share)}%</dd>
          <span className="sub">{num(current.wind_mw)} MW of {num(current.demand_mw)} MW demand</span>
        </div>
        <div className="tile">
          <dt>Wind + solar</dt>
          <dd className="mono">{num(current.renewable_share)}%</dd>
          <span className="sub">solar {num(current.solar_mw)} MW</span>
        </div>
        <div className="tile">
          <dt>Last 24 hours</dt>
          <dd className="mono">{num(current.intensity_24h.min)}-{num(current.intensity_24h.max)}</dd>
          <span className="sub">gCO₂/kWh, average {num(current.intensity_24h.avg)}</span>
        </div>
        <div className="tile">
          <dt>Avg wind share, 24 h</dt>
          <dd className="mono">{num(current.wind_share_24h_avg)}%</dd>
          <span className="sub">of system demand</span>
        </div>
      </dl>
    </section>
  );
}
