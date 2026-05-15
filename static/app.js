/**
 * BTC Trend Prediction Dashboard — Frontend Logic
 */

const REFRESH_INTERVAL = 300; // seconds
let currentTimeframe = '1d';
let dashboardData = null;
let refreshTimer = null;
let countdown = REFRESH_INTERVAL;

// ── Group definitions for display ──────────────────────────────────────────
const GROUP_META = {
  price_structure:      { title: 'Price Structure',        icon: '📊', order: 1 },
  momentum_volatility:  { title: 'Momentum & Volatility',  icon: '⚡', order: 2 },
  macro_sentiment:      { title: 'Macro / Sentiment',      icon: '🌍', order: 3 },
  derivatives:          { title: 'Derivatives & Flows',     icon: '📈', order: 4 },
  liquidation:          { title: 'Liquidation Intel',       icon: '💥', order: 5 },
  session:              { title: 'Session Timing',          icon: '🕐', order: 6 },
};

// ── Fetch Dashboard Data ───────────────────────────────────────────────────
async function fetchDashboard() {
  try {
    const resp = await fetch('/api/dashboard');
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    dashboardData = await resp.json();
    renderDashboard();
    hideLoading();
  } catch (err) {
    console.error('Fetch error:', err);
    document.getElementById('loadingOverlay').querySelector('.loading-text')
      .textContent = `Error: ${err.message}. Retrying…`;
    setTimeout(fetchDashboard, 5000);
  }
}

// ── Render Full Dashboard ──────────────────────────────────────────────────
function renderDashboard() {
  if (!dashboardData) return;

  renderHeader();
  renderTimeframeTabs();
  renderPrediction();
  renderGroups();
  document.getElementById('dashboard').style.display = 'block';
}

// ── Header ─────────────────────────────────────────────────────────────────
function renderHeader() {
  const d = dashboardData;
  const priceEl = document.getElementById('headerPrice');
  const changeEl = document.getElementById('headerChange');

  priceEl.textContent = `$${formatNumber(d.current_price)}`;

  const pct = d.price_change_pct_24h;
  const sign = pct >= 0 ? '+' : '';
  changeEl.textContent = `${sign}$${formatNumber(d.price_change_24h)} (${sign}${pct.toFixed(2)}%)`;
  changeEl.style.color = pct >= 0 ? 'var(--accent-bull)' : 'var(--accent-bear)';

  // Session
  if (d.session) {
    document.getElementById('sessionBadge').textContent = d.session.label;
  }

  // Last updated
  if (d.last_updated) {
    const dt = new Date(d.last_updated);
    document.getElementById('lastUpdated').textContent = `Updated: ${dt.toLocaleTimeString()}`;
  }
}

// ── Timeframe Tabs ─────────────────────────────────────────────────────────
function renderTimeframeTabs() {
  const container = document.getElementById('timeframeTabs');
  container.innerHTML = '';

  if (!dashboardData.predictions) return;

  dashboardData.predictions.forEach(p => {
    const btn = document.createElement('button');
    btn.className = `timeframe-tab${p.timeframe === currentTimeframe ? ' active' : ''}`;
    btn.textContent = p.timeframe_label;
    btn.onclick = () => {
      currentTimeframe = p.timeframe;
      renderTimeframeTabs();
      renderPrediction();
      renderGroups();
    };
    container.appendChild(btn);
  });
}

// ── Prediction Hero ────────────────────────────────────────────────────────
function renderPrediction() {
  const pred = dashboardData.predictions.find(p => p.timeframe === currentTimeframe);
  if (!pred) return;

  const hero = document.getElementById('predictionHero');
  hero.className = `prediction-hero ${pred.direction} fade-in`;

  // Arrow
  const arrows = { bullish: '↑', bearish: '↓', neutral: '→' };
  document.getElementById('heroArrow').textContent = arrows[pred.direction] || '→';

  // Label
  document.getElementById('heroLabel').textContent = pred.direction.toUpperCase();

  // Score
  const scoreEl = document.getElementById('heroScore');
  scoreEl.textContent = (pred.composite_score >= 0 ? '+' : '') + pred.composite_score.toFixed(3);
  scoreEl.style.color = pred.direction === 'bullish' ? 'var(--accent-bull)'
                       : pred.direction === 'bearish' ? 'var(--accent-bear)'
                       : 'var(--accent-neutral)';

  // Move
  document.getElementById('heroMove').textContent = `±${pred.estimated_move_pct.toFixed(2)}%`;

  // Confidence gauge
  const pct = pred.confidence;
  const arcLength = 204;
  const offset = arcLength - (arcLength * pct / 100);
  const gaugeFill = document.getElementById('gaugeFill');
  gaugeFill.style.strokeDashoffset = offset;
  gaugeFill.style.stroke = pct > 60 ? 'var(--accent-bull)' : pct > 40 ? 'var(--accent-neutral)' : 'var(--accent-bear)';
  document.getElementById('gaugeText').textContent = `${pct.toFixed(0)}%`;

  // Price range
  const rangeLow = pred.estimated_range_low;
  const rangeHigh = pred.estimated_range_high;
  const currentPrice = pred.current_price;
  document.getElementById('rangeLow').textContent = `$${formatNumber(rangeLow)}`;
  document.getElementById('rangeHigh').textContent = `$${formatNumber(rangeHigh)}`;

  const rangeSpan = rangeHigh - rangeLow;
  if (rangeSpan > 0) {
    const markerPct = ((currentPrice - rangeLow) / rangeSpan) * 100;
    document.getElementById('rangeMarker').style.left = `${Math.max(2, Math.min(98, markerPct))}%`;
    document.getElementById('rangeFill').style.left = '10%';
    document.getElementById('rangeFill').style.width = '80%';
  }
}

// ── Indicator Groups ───────────────────────────────────────────────────────
function renderGroups() {
  const pred = dashboardData.predictions.find(p => p.timeframe === currentTimeframe);
  if (!pred) return;

  const container = document.getElementById('groupsGrid');
  container.innerHTML = '';

  // Group indicators by group name
  const grouped = {};
  pred.indicators.forEach(ind => {
    if (!grouped[ind.group]) grouped[ind.group] = [];
    grouped[ind.group].push(ind);
  });

  // Sort by order
  const sortedGroups = Object.entries(grouped)
    .sort((a, b) => (GROUP_META[a[0]]?.order || 99) - (GROUP_META[b[0]]?.order || 99));

  sortedGroups.forEach(([groupKey, indicators], idx) => {
    const meta = GROUP_META[groupKey] || { title: groupKey, icon: '📌' };
    const groupScore = pred.groups[groupKey] || 0;
    const signal = groupScore > 0.15 ? 'bullish' : groupScore < -0.15 ? 'bearish' : 'neutral';

    const card = document.createElement('div');
    card.className = `group-card fade-in stagger-${idx + 1}`;

    let indicatorRows = indicators.map(ind => {
      const indSignal = ind.signal || 'neutral';
      const scoreWidth = Math.abs(ind.score) * 50;
      const unavailClass = ind.available ? '' : ' indicator-unavailable';

      return `
        <div class="indicator-row${unavailClass}">
          <span class="indicator-dot ${indSignal}"></span>
          <span class="indicator-name" title="${ind.name}">${ind.name}</span>
          <span class="indicator-label" title="${ind.label}">${ind.label}</span>
          <div class="indicator-score-bar">
            <div class="indicator-score-fill ${indSignal}"
                 style="width:${scoreWidth}%"></div>
          </div>
        </div>`;
    }).join('');

    card.innerHTML = `
      <div class="group-header">
        <span class="group-title">${meta.icon} ${meta.title}</span>
        <span class="group-score ${signal}">${groupScore >= 0 ? '+' : ''}${groupScore.toFixed(2)}</span>
      </div>
      ${indicatorRows}`;

    container.appendChild(card);
  });
}

// ── Utilities ──────────────────────────────────────────────────────────────
function formatNumber(n) {
  if (n == null) return '—';
  if (Math.abs(n) >= 1000) return n.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 });
  return n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function hideLoading() {
  const overlay = document.getElementById('loadingOverlay');
  overlay.classList.add('hidden');
  setTimeout(() => overlay.style.display = 'none', 600);
}

// ── Refresh Logic ──────────────────────────────────────────────────────────
function startRefreshCycle() {
  countdown = REFRESH_INTERVAL;
  const bar = document.getElementById('refreshBar');

  if (refreshTimer) clearInterval(refreshTimer);

  refreshTimer = setInterval(() => {
    countdown--;
    const pct = ((REFRESH_INTERVAL - countdown) / REFRESH_INTERVAL) * 100;
    bar.style.width = `${pct}%`;

    if (countdown <= 0) {
      fetchDashboard();
      countdown = REFRESH_INTERVAL;
    }
  }, 1000);
}

// ── Init ───────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  fetchDashboard().then(() => startRefreshCycle());
});
