import {
  Area, CartesianGrid, ComposedChart, Line, ReferenceArea, ReferenceLine,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { hhmm, num, toMs, when } from "../format.js";

const AXIS = { stroke: "var(--muted)", fontSize: 12, tickLine: false, axisLine: false };

function merge(history, forecast, key) {
  const rows = history.map((p) => ({ t: toMs(p.time), actual: p[key] }));
  const last = rows[rows.length - 1];
  if (last) last.forecast = last.actual; // join the two lines
  forecast.forEach((p) => {
    rows.push({
      t: toMs(p.time),
      forecast: p[key],
      band: key === "intensity" ? [p.low, p.high] : undefined,
    });
  });
  return rows;
}

function ChartTooltip({ active, payload, unit, label }) {
  if (!active || !payload?.length) return null;
  const row = payload[0].payload;
  const isForecast = row.actual == null;
  return (
    <div className="tooltip">
      <div className="tooltip-time">{when(new Date(label).toISOString())}</div>
      <div className="tooltip-value mono">
        {num(isForecast ? row.forecast : row.actual)} {unit}
      </div>
      <div className="tooltip-kind">
        {isForecast ? "Forecast" : "Measured"}
        {isForecast && row.band ? ` · likely ${num(row.band[0])}-${num(row.band[1])}` : ""}
      </div>
    </div>
  );
}

function ticks(rows) {
  if (!rows.length) return [];
  const out = [];
  const start = Math.ceil(rows[0].t / 21600000) * 21600000; // every 6 h
  for (let t = start; t <= rows[rows.length - 1].t; t += 21600000) out.push(t);
  return out;
}

export function IntensityChart({ history, forecast, bestWindow, now }) {
  const rows = merge(history, forecast, "intensity");
  return (
    <figure className="chart">
      <figcaption>
        <h3>Carbon intensity, last 24 h and next 24 h</h3>
        <p className="legend">
          <span className="item"><span className="key key-actual" />Measured</span>
          <span className="item"><span className="key key-forecast" />Forecast</span>
          <span className="item"><span className="key key-band" />Likely range (p10-p90)</span>
          {bestWindow && <span className="item"><span className="key key-green" />Greenest 2 h</span>}
        </p>
      </figcaption>
      <ResponsiveContainer width="100%" height={300}>
        <ComposedChart data={rows} margin={{ top: 8, right: 12, bottom: 0, left: -8 }}>
          <CartesianGrid stroke="var(--grid)" vertical={false} />
          <XAxis dataKey="t" type="number" scale="time" domain={["dataMin", "dataMax"]}
            ticks={ticks(rows)} tickFormatter={hhmm} {...AXIS} />
          <YAxis {...AXIS} width={48} domain={[0, (max) => Math.max(400, Math.ceil(max / 100) * 100)]}
            tickCount={5} allowDecimals={false} />
          <ReferenceLine y={200} stroke="var(--low)" strokeDasharray="2 4" strokeOpacity={0.6} />
          <ReferenceLine y={300} stroke="var(--high)" strokeDasharray="2 4" strokeOpacity={0.6} />
          {bestWindow && (
            <ReferenceArea x1={toMs(bestWindow.start)} x2={toMs(bestWindow.end)}
              fill="var(--low)" fillOpacity={0.12} stroke="none" />
          )}
          <ReferenceLine x={now} stroke="var(--ink)" strokeOpacity={0.5}
            label={{ value: "now", position: "insideTopLeft", fill: "var(--muted)", fontSize: 12 }} />
          <Area dataKey="band" stroke="none" fill="var(--forecast)" fillOpacity={0.15}
            isAnimationActive={false} connectNulls />
          <Line dataKey="actual" stroke="var(--ink)" strokeWidth={2} dot={false}
            isAnimationActive={false} />
          <Line dataKey="forecast" stroke="var(--forecast)" strokeWidth={2} strokeDasharray="5 4"
            dot={false} isAnimationActive={false} />
          <Tooltip content={<ChartTooltip unit="gCO₂/kWh" />} cursor={{ stroke: "var(--muted)" }} />
        </ComposedChart>
      </ResponsiveContainer>
      <p className="chart-note">Dotted lines mark 200 and 300 gCO₂/kWh, the low / moderate / high bands.</p>
    </figure>
  );
}

export function WindChart({ history, forecast, now }) {
  const rows = merge(history, forecast, "wind_share");
  return (
    <figure className="chart">
      <figcaption>
        <h3>Wind share of demand</h3>
        <p className="legend">
          <span className="item"><span className="key key-wind" />Measured</span>
          <span className="item"><span className="key key-wind-fc" />From EirGrid wind forecast</span>
        </p>
      </figcaption>
      <ResponsiveContainer width="100%" height={200}>
        <ComposedChart data={rows} margin={{ top: 8, right: 12, bottom: 0, left: -8 }}>
          <CartesianGrid stroke="var(--grid)" vertical={false} />
          <XAxis dataKey="t" type="number" scale="time" domain={["dataMin", "dataMax"]}
            ticks={ticks(rows)} tickFormatter={hhmm} {...AXIS} />
          <YAxis {...AXIS} width={48} domain={[0, (max) => Math.max(100, Math.ceil(max / 25) * 25)]}
            tickCount={5} allowDecimals={false} tickFormatter={(v) => `${v}%`} />
          <ReferenceLine x={now} stroke="var(--ink)" strokeOpacity={0.5} />
          <Area dataKey="actual" stroke="var(--wind)" strokeWidth={2} fill="var(--wind)"
            fillOpacity={0.12} isAnimationActive={false} />
          <Line dataKey="forecast" stroke="var(--wind)" strokeWidth={2} strokeDasharray="5 4"
            dot={false} isAnimationActive={false} />
          <Tooltip content={<ChartTooltip unit="%" />} cursor={{ stroke: "var(--muted)" }} />
        </ComposedChart>
      </ResponsiveContainer>
    </figure>
  );
}
