const TZ = "Europe/Dublin";

const timeFmt = new Intl.DateTimeFormat("en-IE", { hour: "2-digit", minute: "2-digit", timeZone: TZ, hour12: false });
const dayFmt = new Intl.DateTimeFormat("en-IE", { weekday: "short", timeZone: TZ });

export const toMs = (iso) => new Date(iso).getTime();
export const hhmm = (t) => timeFmt.format(typeof t === "number" ? new Date(t) : new Date(t));

export function dayLabel(iso) {
  const d = new Date(iso);
  const today = dayFmt.format(new Date());
  const tomorrow = dayFmt.format(new Date(Date.now() + 86400000));
  const label = dayFmt.format(d);
  if (label === today) return "today";
  if (label === tomorrow) return "tomorrow";
  return label;
}

export const when = (iso) => `${hhmm(iso)} ${dayLabel(iso)}`;
export const num = (v, digits = 0) =>
  v == null ? "-" : Number(v).toLocaleString("en-IE", { maximumFractionDigits: digits, minimumFractionDigits: digits });

export function grams(g) {
  if (g == null) return "-";
  return g >= 1000 ? `${num(g / 1000, 1)} kg` : `${num(g)} g`;
}

export const BAND_LABEL = { low: "Low carbon", moderate: "Moderate", high: "High carbon" };
