import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { ChartMode } from "../lib/dashboardState";
import type { GroupedUsageDay } from "../lib/usage";
import { compactCredits, fmtCompactNum } from "../lib/format";
import { LoaderBlock } from "./DashboardPrimitives";

const chartColors = {
  input: "rgb(var(--color-input))",
  output: "rgb(var(--color-output))",
  cachedInput: "rgb(var(--color-cached-input))",
  credits: "rgb(var(--color-credit))",
  grid: "rgb(var(--color-border) / 0.55)",
  muted: "rgb(var(--color-muted))",
  hover: "rgb(var(--color-brand) / 0.10)",
  danger: "rgb(var(--color-danger))",
};

export type VisibleChartSeries = {
  credits: boolean;
  uncached: boolean;
  cached: boolean;
  output: boolean;
};

function numericValue(value: unknown) {
  return typeof value === "number" ? value : Number(value || 0);
}

function chartData(days: GroupedUsageDay[]) {
  return days.map((row) => ({
    day: row.label || row.day.slice(5),
    uncached_input_tokens: row.uncached_input_tokens,
    cached_input_tokens: row.cached_input_tokens,
    output_tokens: row.output_tokens,
    total_zar: row.total_zar,
    total_credits: row.total_credits,
    over_safe_daily_spend: false,
  }));
}

function tooltipLabel(name: string) {
  if (name === "Credits" || name === "total_credits") return "Credits";
  if (name === "uncached_input_tokens") return "Uncached input";
  if (name === "cached_input_tokens") return "Cached input";
  if (name === "output_tokens") return "Output";
  return name;
}

function UsageTooltip({
  active,
  label,
  payload,
  safeDailySpend,
}: {
  active?: boolean;
  label?: string;
  payload?: Array<{ color?: string; dataKey?: string; name?: string; value?: unknown; payload?: { total_credits?: number; over_safe_daily_spend?: boolean } }>;
  safeDailySpend?: number | null;
}) {
  if (!active || !payload?.length) return null;
  const credits = numericValue(payload[0]?.payload?.total_credits);
  const overSafeDailySpend = Boolean(payload[0]?.payload?.over_safe_daily_spend);
  return (
    <div className="min-w-56 rounded-md border border-border bg-panel p-3 text-sm text-ink shadow-xl">
      <div className="font-semibold">{label}</div>
      {safeDailySpend ? (
        <div className={`mt-1 text-xs font-semibold ${overSafeDailySpend ? "text-danger" : "text-muted"}`}>
          {overSafeDailySpend
            ? `${compactCredits(credits)} is over the safe daily spend of ${compactCredits(safeDailySpend)}.`
            : `${compactCredits(credits)} is inside the safe daily spend of ${compactCredits(safeDailySpend)}.`}
        </div>
      ) : null}
      <div className="mt-2 grid gap-1">
        {payload.map((item) => {
          const key = item.dataKey || item.name || "";
          const value = numericValue(item.value);
          const isCredits = key === "total_credits" || item.name === "Credits";
          return (
            <div key={key} className="flex items-center justify-between gap-4">
              <span className="inline-flex min-w-0 items-center gap-2 text-muted">
                <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: item.color }} />
                <span className="truncate">{tooltipLabel(key)}</span>
              </span>
              <span className="font-semibold text-ink">{isCredits ? compactCredits(value) : fmtCompactNum.format(value)}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function CreditDot(props: { cx?: number; cy?: number; payload?: { over_safe_daily_spend?: boolean } }) {
  if (typeof props.cx !== "number" || typeof props.cy !== "number") return null;
  return (
    <circle
      cx={props.cx}
      cy={props.cy}
      fill={props.payload?.over_safe_daily_spend ? chartColors.danger : chartColors.credits}
      r={props.payload?.over_safe_daily_spend ? 4 : 2.5}
      stroke="rgb(var(--color-panel))"
      strokeWidth={1.5}
    />
  );
}

export function DashboardChart({
  rows,
  mode,
  safeDailySpend,
  visibleSeries,
}: {
  rows: GroupedUsageDay[];
  mode: ChartMode;
  safeDailySpend?: number | null;
  visibleSeries?: VisibleChartSeries;
}) {
  const series = visibleSeries || { credits: true, uncached: true, cached: true, output: true };
  const data = chartData(rows).map((row) => ({
    ...row,
    over_safe_daily_spend: Boolean(safeDailySpend && row.total_credits > safeDailySpend),
  }));
  if (!data.length) return <LoaderBlock label="No chart data" />;

  const common = (cursor?: false | { fill: string }) => (
    <>
      <CartesianGrid stroke={chartColors.grid} vertical={false} />
      <XAxis dataKey="day" stroke={chartColors.muted} fontSize={12} tickLine={false} axisLine={false} />
      <YAxis yAxisId="tokens" stroke={chartColors.muted} fontSize={12} tickLine={false} axisLine={false} tickFormatter={(value) => fmtCompactNum.format(numericValue(value))} />
      <YAxis yAxisId="credits" orientation="right" stroke={chartColors.muted} fontSize={12} tickLine={false} axisLine={false} tickFormatter={(value) => compactCredits(numericValue(value))} />
      <Tooltip
        content={<UsageTooltip safeDailySpend={safeDailySpend} />}
        cursor={cursor}
      />
      <Legend iconType="circle" wrapperStyle={{ fontSize: 12, paddingTop: 10 }} />
      {safeDailySpend ? (
        <ReferenceLine
          yAxisId="credits"
          y={safeDailySpend}
          stroke={chartColors.danger}
          strokeDasharray="5 4"
          label={{ value: "Safe daily spend", fill: chartColors.muted, fontSize: 12, position: "insideTopRight" }}
        />
      ) : null}
    </>
  );

  if (mode === "bar") {
    return (
      <div className="h-[280px] sm:h-[320px] xl:h-[360px]">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} barGap={6}>
            {common({ fill: chartColors.hover })}
            {series.uncached ? <Bar yAxisId="tokens" dataKey="uncached_input_tokens" name="Uncached input" fill={chartColors.input} radius={[5, 5, 0, 0]} /> : null}
            {series.cached ? <Bar yAxisId="tokens" dataKey="cached_input_tokens" name="Cached input" fill={chartColors.cachedInput} radius={[5, 5, 0, 0]} /> : null}
            {series.output ? <Bar yAxisId="tokens" dataKey="output_tokens" name="Output" fill={chartColors.output} radius={[5, 5, 0, 0]} /> : null}
            {series.credits ? (
              <Bar yAxisId="credits" dataKey="total_credits" name="Credits" fill={chartColors.credits} radius={[5, 5, 0, 0]}>
                {data.map((entry) => (
                  <Cell key={entry.day} fill={entry.over_safe_daily_spend ? chartColors.danger : chartColors.credits} />
                ))}
              </Bar>
            ) : null}
          </BarChart>
        </ResponsiveContainer>
      </div>
    );
  }

  return (
    <div className="h-[280px] sm:h-[320px] xl:h-[360px]">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data}>
          {common(false)}
          {series.uncached ? <Line yAxisId="tokens" type="monotone" dataKey="uncached_input_tokens" name="Uncached input" stroke={chartColors.input} strokeWidth={3} dot={false} /> : null}
          {series.cached ? <Line yAxisId="tokens" type="monotone" dataKey="cached_input_tokens" name="Cached input" stroke={chartColors.cachedInput} strokeWidth={2} strokeDasharray="6 4" dot={false} /> : null}
          {series.output ? <Line yAxisId="tokens" type="monotone" dataKey="output_tokens" name="Output" stroke={chartColors.output} strokeWidth={3} dot={false} /> : null}
          {series.credits ? <Line yAxisId="credits" type="monotone" dataKey="total_credits" name="Credits" stroke={chartColors.credits} strokeWidth={3} dot={<CreditDot />} activeDot={{ r: 5 }} /> : null}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export function CreditAreaChart({ rows }: { rows: GroupedUsageDay[] }) {
  const data = chartData(rows);
  return (
    <div className="h-[150px] sm:h-[170px] xl:h-[190px]">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data}>
        <CartesianGrid stroke={chartColors.grid} vertical={false} />
        <XAxis dataKey="day" stroke={chartColors.muted} fontSize={12} tickLine={false} axisLine={false} />
        <YAxis stroke={chartColors.muted} fontSize={12} tickLine={false} axisLine={false} tickFormatter={(value) => compactCredits(numericValue(value))} />
        <Tooltip
        contentStyle={{
          background: "rgb(var(--color-panel))",
          border: "1px solid rgb(var(--color-border))",
          borderRadius: 6,
          boxShadow: "0 16px 48px rgb(0 0 0 / 0.16)",
          color: "rgb(var(--color-ink))",
        }}
          formatter={(value) => [compactCredits(numericValue(value)), "Credits"]}
        />
        <Area type="monotone" dataKey="total_credits" name="Credits" stroke={chartColors.credits} fill={chartColors.credits} fillOpacity={0.18} strokeWidth={3} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
