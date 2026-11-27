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

// ── Detail modal ─────────────────────────────────────────
(function initDetailModal() {
  const overlay = document.getElementById('detail-overlay');
  const titleEl = document.getElementById('detail-title');
  const thead = document.getElementById('detail-thead');
  const tbody = document.getElementById('detail-tbody');
  const closeBtn = document.getElementById('detail-close');
  if (!overlay) return;

  function openModal(detail) {
    titleEl.textContent = detail.title || '';

    // Build header
    thead.innerHTML = '<tr>' +
      detail.columns.map(col => '<th>' + escapeHtml(col) + '</th>').join('') +
      '</tr>';

    // Build rows
    tbody.innerHTML = detail.rows.map(row => {
      const cells = detail.columns.map(col => {
        if (col === '#') {
          return '<td class="num-col"><a href="' + escapeAttr(row.url) + '" target="_blank" rel="noopener">#' + escapeHtml(String(row.number)) + '</a></td>';
        }
        if (col === 'Title') {
          return '<td>' + escapeHtml(row.title || '') + '</td>';
        }
        if (col === detail.sort_column) {
          return '<td class="num-col">' + escapeHtml(row.sort_value != null ? String(row.sort_value) : '—') + '</td>';
        }
        // Extra columns
        const key = col.toLowerCase().replace(/ /g, '_');
        const val = (row.extra && row.extra[key]) != null ? row.extra[key] : '—';
        return '<td>' + escapeHtml(String(val)) + '</td>';
      });
      return '<tr>' + cells.join('') + '</tr>';
    }).join('');

    overlay.classList.add('open');
  }

  function closeModal() {
    overlay.classList.remove('open');
  }

  function escapeHtml(s) {
    const div = document.createElement('div');
    div.appendChild(document.createTextNode(s));
    return div.innerHTML;
  }

  function escapeAttr(s) {
    return s.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  // Card click handler (delegated)
  document.addEventListener('click', function(e) {
    const card = e.target.closest('[data-detail-key]');
    if (!card) return;
    // Don't intercept clicks on links or info icons inside the card
    if (e.target.closest('a') || e.target.closest('.card-info')) return;

    const key = card.getAttribute('data-detail-key');
    if (typeof DETAILS !== 'undefined' && DETAILS[key]) {
      openModal(DETAILS[key]);
    }
  });

  // Close handlers
  closeBtn.addEventListener('click', closeModal);
  overlay.addEventListener('click', function(e) {
    if (e.target === overlay) closeModal();
  });
  document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape' && overlay.classList.contains('open')) closeModal();
  });
})();

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
