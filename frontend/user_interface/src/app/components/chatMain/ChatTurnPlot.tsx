import {
  Bar,
  BarChart,
  Brush,
  CartesianGrid,
  Line,
  LineChart,
  Scatter,
  ScatterChart,
  XAxis,
  YAxis,
} from "recharts";

import {
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
} from "../ui/chart";

type PlotSeries = {
  key: string;
  label: string;
  type?: "line" | "bar" | "scatter";
  color?: string;
};

type PlotPayload = {
  kind: "chart";
  library?: string;
  chart_type: "line" | "bar" | "scatter" | "histogram";
  title?: string;
  x?: string;
  y?: string;
  x_type?: "numeric" | "category";
  points: Record<string, unknown>[];
  series: PlotSeries[];
  interactive?: Record<string, unknown>;
};

const FALLBACK_COLORS = [
  "#111111",
  "#374151",
  "#4b5563",
  "#6b7280",
  "#9ca3af",
  "#1f2937",
];

function toNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  const parsed = Number(String(value ?? "").trim());
  return Number.isFinite(parsed) ? parsed : null;
}

function normalizeSeries(raw: unknown): PlotSeries[] {
  if (!Array.isArray(raw)) {
    return [];
  }
  const result: PlotSeries[] = [];
  for (const item of raw.slice(0, 6)) {
    if (!item || typeof item !== "object") {
      continue;
    }
    const row = item as Record<string, unknown>;
    const key = String(row.key || row.data_key || "").trim();
    if (!key) {
      continue;
    }
    const label = String(row.label || key).trim() || key;
    const typeValue = String(row.type || "").trim().toLowerCase();
    const type =
      typeValue === "line" || typeValue === "bar" || typeValue === "scatter"
        ? (typeValue as PlotSeries["type"])
        : undefined;
    const color = String(row.color || "").trim();
    result.push({ key, label, type, color });
  }
  return result;
}

function normalizePoints(raw: unknown): Record<string, unknown>[] {
  if (!Array.isArray(raw)) {
    return [];
  }
  const rows: Record<string, unknown>[] = [];
  for (const item of raw.slice(0, 1000)) {
    if (!item || typeof item !== "object") {
      continue;
    }
    const point = item as Record<string, unknown>;
    const x = point.x;
    if (x === undefined || x === null) {
      continue;
    }
    const normalized: Record<string, unknown> = {
      x: typeof x === "number" ? x : String(x),
    };
    let metricCount = 0;
    for (const [key, value] of Object.entries(point)) {
      if (key === "x") {
        continue;
      }
      if (typeof value === "number" && Number.isFinite(value)) {
        normalized[key] = value;
        metricCount += 1;
        continue;
      }
      const parsed = toNumber(value);
      if (parsed !== null) {
        normalized[key] = parsed;
        metricCount += 1;
      }
    }
    if (metricCount > 0) {
      rows.push(normalized);
    }
  }
  return rows;
}

function normalizePlot(plot: Record<string, unknown> | null | undefined): PlotPayload | null {
  if (!plot || typeof plot !== "object") {
    return null;
  }
  const kind = String(plot.kind || "").trim().toLowerCase();
  const chartType = String(plot.chart_type || "").trim().toLowerCase();
  if (kind !== "chart") {
    return null;
  }
  if (!["line", "bar", "scatter", "histogram"].includes(chartType)) {
    return null;
  }
  const points = normalizePoints(plot.points);
  if (!points.length) {
    return null;
  }
  let series = normalizeSeries(plot.series);
  if (!series.length) {
    const fallbackKey = String(plot.y || "y").trim() || "y";
    series = [{ key: fallbackKey, label: fallbackKey, type: chartType as PlotSeries["type"] }];
  }
  const availableKeys = new Set(points.flatMap((point) => Object.keys(point)));
  series = series.filter((item) => availableKeys.has(item.key));
  if (!series.length) {
    return null;
  }

  const xTypeRaw = String(plot.x_type || "").trim().toLowerCase();
  const inferredNumericX = points.every((point) => toNumber(point.x) !== null);
  const xType =
    xTypeRaw === "numeric" || xTypeRaw === "category"
      ? (xTypeRaw as "numeric" | "category")
      : inferredNumericX
        ? "numeric"
        : "category";
  return {
    kind: "chart",
    library: String(plot.library || "recharts"),
    chart_type: chartType as PlotPayload["chart_type"],
    title: String(plot.title || "").trim(),
    x: String(plot.x || "").trim(),
    y: String(plot.y || "").trim(),
    x_type: xType,
    points,
    series,
    interactive:
      plot.interactive && typeof plot.interactive === "object"
        ? (plot.interactive as Record<string, unknown>)
        : {},
  };
}

function colorForSeries(series: PlotSeries, index: number) {
  return series.color || FALLBACK_COLORS[index % FALLBACK_COLORS.length];
}

type ChatTurnPlotProps = {
  plot?: Record<string, unknown> | null;
};

function ChatTurnPlot({ plot }: ChatTurnPlotProps) {
  const parsed = normalizePlot(plot);
  if (!parsed) {
    return null;
  }
  const showBrush =
    parsed.chart_type !== "scatter" &&
    parsed.points.length > 24 &&
    parsed.interactive?.brush !== false;
  const labelX = parsed.x || "x";

  if (parsed.chart_type === "scatter") {
    const ySeries = parsed.series[0];
    const data = parsed.points
      .map((point) => ({
        x: toNumber(point.x),
        y: toNumber(point[ySeries.key] ?? point.y),
      }))
      .filter((point) => point.x !== null && point.y !== null) as Array<{ x: number; y: number }>;
    if (!data.length) {
      return null;
    }
    return (
      <div className="rounded-2xl border border-black/[0.08] bg-[#fafafa] p-3">
        <div className="mb-2 flex items-center justify-between gap-2">
          <p className="truncate text-[12px] font-semibold text-[#1d1d1f]">
            {parsed.title || "scatter chart"}
          </p>
          <span className="rounded-full border border-black/[0.08] bg-white px-2 py-0.5 text-[10px] text-[#6e6e73]">
            Interactive
          </span>
        </div>
        <ChartContainer
          className="h-[280px] w-full rounded-xl border border-black/[0.06] bg-white p-2"
          config={{
            [ySeries.key]: {
              label: ySeries.label,
              color: colorForSeries(ySeries, 0),
            },
          }}
        >
          <ScatterChart margin={{ top: 8, right: 12, left: 0, bottom: 8 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="x" name={labelX} type="number" />
            <YAxis dataKey="y" name={ySeries.label} />
            <ChartTooltip content={<ChartTooltipContent />} />
            <Scatter data={data} fill={colorForSeries(ySeries, 0)} />
          </ScatterChart>
        </ChartContainer>
      </div>
    );
  }

  const data = parsed.points.map((point) => {
    const row: Record<string, string | number> = {
      x:
        parsed.x_type === "numeric"
          ? (toNumber(point.x) ?? String(point.x))
          : String(point.x),
    };
    for (const [key, value] of Object.entries(point)) {
      if (key === "x") {
        continue;
      }
      const numeric = toNumber(value);
      if (numeric !== null) {
        row[key] = numeric;
      }
    }
    return row;
  });

  const chartConfig = Object.fromEntries(
    parsed.series.map((series, index) => [
      series.key,
      {
        label: series.label,
        color: colorForSeries(series, index),
      },
    ]),
  );

  return (
    <div className="rounded-2xl border border-black/[0.08] bg-[#fafafa] p-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <p className="truncate text-[12px] font-semibold text-[#1d1d1f]">
          {parsed.title || `${parsed.chart_type} chart`}
        </p>
        <span className="rounded-full border border-black/[0.08] bg-white px-2 py-0.5 text-[10px] text-[#6e6e73]">
          Interactive
        </span>
      </div>
      <ChartContainer
        className="h-[280px] w-full rounded-xl border border-black/[0.06] bg-white p-2"
        config={chartConfig}
      >
        {parsed.chart_type === "line" ? (
          <LineChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 8 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="x" type={parsed.x_type === "numeric" ? "number" : "category"} />
            <YAxis />
            <ChartTooltip content={<ChartTooltipContent />} />
            {parsed.series.length > 1 ? (
              <ChartLegend content={<ChartLegendContent />} />
            ) : null}
            {parsed.series.map((series, index) => (
              <Line
                key={series.key}
                dataKey={series.key}
                stroke={colorForSeries(series, index)}
                strokeWidth={2.2}
                dot={false}
                connectNulls
              />
            ))}
            {showBrush ? <Brush dataKey="x" height={20} stroke="#111111" /> : null}
          </LineChart>
        ) : (
          <BarChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 8 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="x" type={parsed.x_type === "numeric" ? "number" : "category"} />
            <YAxis />
            <ChartTooltip content={<ChartTooltipContent />} />
            {parsed.series.length > 1 ? (
              <ChartLegend content={<ChartLegendContent />} />
            ) : null}
            {parsed.series.map((series, index) => (
              <Bar
                key={series.key}
                dataKey={series.key}
                fill={colorForSeries(series, index)}
                radius={[4, 4, 0, 0]}
              />
            ))}
            {showBrush ? <Brush dataKey="x" height={20} stroke="#111111" /> : null}
          </BarChart>
        )}
      </ChartContainer>
    </div>
  );
}

export { ChatTurnPlot };
