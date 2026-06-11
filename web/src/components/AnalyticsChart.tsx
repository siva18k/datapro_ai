import {
  ArcElement,
  BarController,
  BarElement,
  CategoryScale,
  Chart as ChartJS,
  Legend,
  LinearScale,
  LineController,
  LineElement,
  PieController,
  PointElement,
  Title,
  Tooltip,
} from "chart.js";
import { useEffect, useRef } from "react";
import type { ChartType } from "../utils/analyticsData";

ChartJS.register(
  CategoryScale,
  LinearScale,
  BarController,
  BarElement,
  LineController,
  LineElement,
  PointElement,
  PieController,
  ArcElement,
  Title,
  Tooltip,
  Legend,
);

interface Props {
  chartType: ChartType;
  title: string;
  labels: string[];
  values: number[];
  valueLabel: string;
}

export function AnalyticsChart({ chartType, title, labels, values, valueLabel }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const chartRef = useRef<ChartJS<"bar" | "line" | "pie"> | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    chartRef.current?.destroy();

    const color = chartType === "pie" ? pieColors(labels.length) : undefined;

    chartRef.current = new ChartJS(canvas, {
      type: chartType,
      data: {
        labels,
        datasets: [
          {
            label: valueLabel,
            data: values,
            backgroundColor:
              color ??
              labels.map((_, i) => `rgba(37, 99, 235, ${0.45 + (i % 3) * 0.15})`),
            borderColor: chartType === "line" ? "rgb(37, 99, 235)" : undefined,
            borderWidth: chartType === "line" ? 2 : 1,
            tension: 0.25,
            fill: chartType === "line",
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: chartType === "pie" },
          title: { display: false },
        },
        scales:
          chartType === "pie"
            ? {}
            : {
                y: { beginAtZero: true },
              },
      },
    });

    return () => {
      chartRef.current?.destroy();
      chartRef.current = null;
    };
  }, [chartType, labels, values, valueLabel]);

  return (
    <div className="analytics-chart-wrap">
      <h3 className="analytics-widget-title">{title}</h3>
      <div className="analytics-chart-canvas">
        <canvas ref={canvasRef} />
      </div>
    </div>
  );
}

function pieColors(n: number): string[] {
  const base = [
    "rgba(37, 99, 235, 0.75)",
    "rgba(16, 185, 129, 0.75)",
    "rgba(245, 158, 11, 0.75)",
    "rgba(239, 68, 68, 0.75)",
    "rgba(139, 92, 246, 0.75)",
    "rgba(236, 72, 153, 0.75)",
    "rgba(14, 165, 233, 0.75)",
    "rgba(132, 204, 22, 0.75)",
  ];
  return Array.from({ length: n }, (_, i) => base[i % base.length]);
}
