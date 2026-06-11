import { cn } from "@/lib/utils";
import type { TrendBucket } from "@/lib/trendRollup";

/**
 * TrendChart — sentiment line + volume bars over time buckets.
 *
 * Hand-rolled inline SVG (no chart dependency — matches the Sparkline atom
 * convention, DESIGN_SYSTEM §3.6). The purple polyline is net sentiment on a
 * fixed [-1, +1] axis; light bars behind are mention volume. Per-point value
 * labels and per-bar volume numbers drop out as the bucket count grows so a
 * dense Week view stays legible. Pure/presentational — the Trend page owns the
 * data fetch and rollup; tested in TrendChart.test.tsx.
 */

export interface TrendChartProps {
  buckets: TrendBucket[];
  width?: number;
  height?: number;
  className?: string;
}

function fmtNet(v: number): string {
  return (v >= 0 ? "+" : "−") + Math.abs(v).toFixed(2);
}

export function TrendChart({
  buckets,
  width = 980,
  height = 260,
  className,
}: TrendChartProps): JSX.Element {
  if (buckets.length === 0) {
    return (
      <svg
        width={width}
        height={height}
        className={cn("max-w-full", className)}
        aria-label="no trend data"
      />
    );
  }

  const padL = 42;
  const padR = 16;
  const padT = 18;
  const padB = 46;
  const n = buckets.length;
  const iw = width - padL - padR;
  const ih = height - padT - padB;

  const x = (i: number): number => (n === 1 ? padL + iw / 2 : padL + (i * iw) / (n - 1));
  const yNet = (v: number): number => padT + ih / 2 - v * (ih / 2);

  const maxVol = Math.max(...buckets.map((b) => b.vol), 1);
  const barW = Math.max(4, Math.min(26, iw / n - 6));
  const showValueLabels = n <= 18;
  const showVolNums = n <= 24;
  const xEvery = n > 26 ? Math.ceil(n / 26) : 1;

  const linePoints = buckets
    .map((b, i) => `${x(i).toFixed(1)},${yNet(b.net).toFixed(1)}`)
    .join(" ");

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className={cn("max-w-full", className)}
      aria-label={`trend, ${n} ${n === 1 ? "point" : "points"}`}
    >
      {/* y gridlines + ticks at +1 / 0 / -1 */}
      {[1, 0, -1].map((t) => (
        <g key={t}>
          <line
            x1={padL}
            y1={yNet(t)}
            x2={width - padR}
            y2={yNet(t)}
            stroke={t === 0 ? "var(--aw-fg-muted)" : "var(--aw-border)"}
            strokeWidth={1}
            strokeDasharray={t === 0 ? undefined : "2 3"}
          />
          <text
            x={padL - 8}
            y={yNet(t) + 3}
            textAnchor="end"
            fontSize={10}
            fill="var(--aw-fg-muted)"
          >
            {t > 0 ? "+1" : t < 0 ? "−1" : "0"}
          </text>
        </g>
      ))}

      {/* volume bars */}
      {buckets.map((b, i) => {
        const bh = (b.vol / maxVol) * (ih * 0.55);
        const bx = x(i) - barW / 2;
        const by = padT + ih - bh;
        return (
          <g key={`bar-${i}`}>
            <rect
              x={bx.toFixed(1)}
              y={by.toFixed(1)}
              width={barW.toFixed(1)}
              height={bh.toFixed(1)}
              rx={2}
              fill="var(--aw-accent-soft)"
              stroke="var(--aw-accent)"
              strokeWidth={0.5}
            />
            {showVolNums && (
              <text
                x={x(i)}
                y={by - 4}
                textAnchor="middle"
                fontSize={9}
                fill="var(--aw-fg-muted)"
              >
                {b.vol}
              </text>
            )}
          </g>
        );
      })}

      {/* sentiment line */}
      <polyline
        points={linePoints}
        fill="none"
        stroke="var(--aw-accent)"
        strokeWidth={n > 30 ? 1.5 : 2}
        strokeLinejoin="round"
        strokeLinecap="round"
      />

      {/* points + value labels */}
      {buckets.map((b, i) => {
        const cy = yNet(b.net);
        const above = b.net <= 0.6;
        const ly = above ? cy - 9 : cy + 15;
        return (
          <g key={`pt-${i}`}>
            {showValueLabels && (
              <>
                <rect
                  x={x(i) - 15}
                  y={ly - 9}
                  width={30}
                  height={13}
                  rx={3}
                  fill="var(--aw-surface)"
                  opacity={0.85}
                />
                <text
                  x={x(i)}
                  y={ly}
                  textAnchor="middle"
                  fontSize={10}
                  fontWeight={600}
                  fill="var(--aw-accent)"
                >
                  {fmtNet(b.net)}
                </text>
              </>
            )}
            <circle cx={x(i)} cy={cy} r={n > 30 ? 2 : 3} fill="var(--aw-accent)" />
          </g>
        );
      })}

      {/* x labels (thinned when dense) */}
      {buckets.map((b, i) =>
        i % xEvery === 0 ? (
          <text
            key={`x-${i}`}
            x={x(i)}
            y={height - padB + 18}
            textAnchor="middle"
            fontSize={10}
            fill="var(--aw-fg-muted)"
          >
            {b.label}
          </text>
        ) : null,
      )}
    </svg>
  );
}
