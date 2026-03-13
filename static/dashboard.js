/**
 * Dashboard chart initialization.
 * Reads from the global TRENDS object injected by the template.
 */

const CHART_COLORS = {
  accent: '#6c8cff',
  accentDim: 'rgba(108, 140, 255, 0.15)',
  green: '#4ade80',
  greenDim: 'rgba(74, 222, 128, 0.15)',
  amber: '#fbbf24',
  red: '#f87171',
  gridColor: 'rgba(255, 255, 255, 0.06)',
  tickColor: '#8b8fa3',
};

// Shared chart defaults
Chart.defaults.color = CHART_COLORS.tickColor;
Chart.defaults.font.size = 11;
Chart.defaults.plugins.legend.display = false;

function sparklineOptions(yMin) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    scales: {
      x: { display: false },
      y: {
        display: false,
        min: yMin,
        beginAtZero: yMin === undefined,
      },
    },
    plugins: {
      tooltip: {
        enabled: true,
        callbacks: {
          title: (items) => TRENDS.dates[items[0].dataIndex] || '',
        },
      },
    },
    elements: {
      point: { radius: 0, hoverRadius: 4 },
      line: { borderWidth: 2, tension: 0.3 },
    },
  };
}

function makeSparkline(canvasId, data, color, fillColor) {
  const canvas = document.getElementById(canvasId);
  if (!canvas || !data || data.every((v) => v === null)) return;

  new Chart(canvas, {
    type: 'line',
    data: {
      labels: TRENDS.dates,
      datasets: [{
        data: data,
        borderColor: color || CHART_COLORS.accent,
        backgroundColor: fillColor || CHART_COLORS.accentDim,
        fill: true,
      }],
    },
    options: sparklineOptions(),
  });
}

// Initialize sparklines if we have trend data
if (TRENDS && TRENDS.dates && TRENDS.dates.length > 0) {
  makeSparkline('chart-issues-open', TRENDS.issues_open);
  makeSparkline('chart-triage-30d', TRENDS.issues_median_triage_days_30d, CHART_COLORS.amber, 'rgba(251, 191, 36, 0.15)');
  makeSparkline('chart-triage-1y', TRENDS.issues_median_triage_days_1y, CHART_COLORS.amber, 'rgba(251, 191, 36, 0.15)');
  makeSparkline('chart-prs-open', TRENDS.prs_open);
  makeSparkline('chart-prs-merged', TRENDS.prs_merged_30d, CHART_COLORS.green, CHART_COLORS.greenDim);
  makeSparkline('chart-first-review', TRENDS.prs_median_hours_to_first_review, CHART_COLORS.amber, 'rgba(251, 191, 36, 0.15)');
  makeSparkline('chart-time-merge', TRENDS.prs_median_hours_to_merge);
}
