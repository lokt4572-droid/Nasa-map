/**
 * Minimal dependency-free SVG line chart with real axes and units.
 * Gaps (null values) break the line: missing data is never interpolated.
 */
export interface Series {
  label: string;
  color: string;
  values: (number | null)[];
}

interface Props {
  x: number[];
  series: Series[];
  xLabel: string;
  yLabel: string;
  formatX?: (v: number) => string;
  height?: number;
  bars?: boolean;
}

function niceTicks(min: number, max: number, count = 4): number[] {
  if (!Number.isFinite(min) || !Number.isFinite(max)) return [];
  if (min === max) return [min];
  const step0 = (max - min) / count;
  const mag = Math.pow(10, Math.floor(Math.log10(step0)));
  const step = [1, 2, 5, 10].map((k) => k * mag).find((s) => s >= step0) ?? step0;
  const out: number[] = [];
  for (let v = Math.ceil(min / step) * step; v <= max + step * 1e-9; v += step) out.push(Number(v.toPrecision(12)));
  return out;
}

export default function LineChart({ x, series, xLabel, yLabel, formatX, height = 150, bars = false }: Props) {
  const W = 300;
  const H = height;
  const m = { l: 42, r: 8, t: 8, b: 30 };
  const all = series.flatMap((s) => s.values.filter((v): v is number => v !== null && Number.isFinite(v)));
  if (x.length < 2 || all.length === 0) return <div className="empty">No data to plot.</div>;
  let yMin = Math.min(...all);
  let yMax = Math.max(...all);
  if (bars) yMin = Math.min(0, yMin);
  if (yMin === yMax) {
    yMin -= 1;
    yMax += 1;
  }
  const xMin = x[0]!;
  const xMax = x[x.length - 1]!;
  const sx = (v: number) => m.l + ((v - xMin) / (xMax - xMin || 1)) * (W - m.l - m.r);
  const sy = (v: number) => H - m.b - ((v - yMin) / (yMax - yMin)) * (H - m.t - m.b);
  const fx = formatX ?? ((v: number) => String(Math.round(v)));
  return (
    <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${yLabel} vs ${xLabel}`}>
      {niceTicks(yMin, yMax).map((t) => (
        <g key={`y${t}`}>
          <line x1={m.l} x2={W - m.r} y1={sy(t)} y2={sy(t)} className="chart__grid" />
          <text x={m.l - 4} y={sy(t) + 3} className="chart__tick" textAnchor="end">
            {Math.abs(t) >= 1000 ? `${(t / 1000).toFixed(1)}k` : t}
          </text>
        </g>
      ))}
      {niceTicks(xMin, xMax, 3).map((t) => (
        <text key={`x${t}`} x={sx(t)} y={H - m.b + 12} className="chart__tick" textAnchor="middle">
          {fx(t)}
        </text>
      ))}
      <text x={(W + m.l) / 2} y={H - 4} className="chart__label" textAnchor="middle">
        {xLabel}
      </text>
      <text x={10} y={H / 2} className="chart__label" textAnchor="middle" transform={`rotate(-90 10 ${H / 2})`}>
        {yLabel}
      </text>
      {series.map((s) => {
        if (bars) {
          const bw = Math.max(1, (W - m.l - m.r) / x.length - 1);
          return s.values.map((v, i) =>
            v === null ? null : (
              <rect key={`${s.label}${i}`} x={sx(x[i]!) - bw / 2} y={Math.min(sy(v), sy(0))} width={bw} height={Math.abs(sy(v) - sy(0))} fill={s.color} />
            ),
          );
        }
        const segs: string[] = [];
        let cur = "";
        s.values.forEach((v, i) => {
          if (v === null || !Number.isFinite(v)) {
            if (cur) segs.push(cur);
            cur = "";
          } else cur += `${cur ? "L" : "M"}${sx(x[i]!).toFixed(1)},${sy(v).toFixed(1)}`;
        });
        if (cur) segs.push(cur);
        return segs.map((d, k) => <path key={`${s.label}${k}`} d={d} fill="none" stroke={s.color} strokeWidth={1.6} />);
      })}
    </svg>
  );
}
