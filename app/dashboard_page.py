def get_dashboard_html() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>FaceDedup Dashboard</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
    <style>
        body { font-family: 'Inter', system-ui, -apple-system, sans-serif; }
        .card { background: #1f2937; border-radius: 12px; border: 1px solid #374151; }
        .pill { display: inline-flex; align-items: center; gap: 6px; padding: 4px 12px; border-radius: 9999px; font-size: 12px; font-weight: 500; }
        .pill-green { background: #064e3b; color: #6ee7b7; }
        .pill-red { background: #7f1d1d; color: #fca5a5; }
        .pill-yellow { background: #78350f; color: #fde68a; }
        .pill-gray { background: #374151; color: #9ca3af; }
        .status-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
        .dot-green { background: #10b981; }
        .dot-red { background: #ef4444; }
        .dot-yellow { background: #f59e0b; }
        .dot-gray { background: #6b7280; }
        .spinner { border: 3px solid #374151; border-top: 3px solid #3b82f6; border-radius: 50%; width: 20px; height: 20px; animation: spin 0.8s linear infinite; display: inline-block; }
        @keyframes spin { to { transform: rotate(360deg); } }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
        .animate-pulse-slow { animation: pulse 2s ease-in-out infinite; }
        .badge { padding: 2px 8px; border-radius: 6px; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; }
        .badge-success { background: #064e3b; color: #6ee7b7; }
        .badge-failed { background: #78350f; color: #fde68a; }
        .badge-error { background: #7f1d1d; color: #fca5a5; }
        .event-row:hover { background: #1f2937; }
        .table-header { position: sticky; top: 0; background: #111827; z-index: 10; }
        ::-webkit-scrollbar { width: 6px; height: 6px; }
        ::-webkit-scrollbar-track { background: #1f2937; }
        ::-webkit-scrollbar-thumb { background: #4b5563; border-radius: 3px; }
    </style>
</head>
<body class="bg-gray-900 text-gray-100 min-h-screen">

    <!-- Header -->
    <header class="bg-gray-950 border-b border-gray-800">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 py-4">
            <div class="flex flex-wrap items-center justify-between gap-4">
                <div class="flex items-center gap-3">
                    <div class="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center">
                        <svg class="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"/>
                        </svg>
                    </div>
                    <div>
                        <h1 class="text-xl font-bold text-white">FaceDedup Dashboard</h1>
                        <p class="text-xs text-gray-500">Real-time monitoring &amp; analytics</p>
                    </div>
                    <span class="bg-blue-600 text-xs font-semibold px-2 py-0.5 rounded-full text-white">v1.0.0</span>
                </div>
                <div class="flex flex-wrap items-center gap-3">
                    <a href="/" class="text-sm text-gray-400 hover:text-white transition">&#8592; API Docs</a>
                    <div class="h-4 w-px bg-gray-700"></div>
                    <div class="relative">
                        <input type="password" id="apiKey" placeholder="X-API-Key"
                            class="bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm font-mono text-gray-300 w-48 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none pr-12">
                        <button onclick="toggleKeyVis()" id="keyToggleBtn" class="absolute right-2 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300 text-xs">show</button>
                    </div>
                    <button onclick="saveKey()" class="bg-blue-600 hover:bg-blue-700 text-white px-3 py-1.5 rounded-lg text-sm font-medium transition">Save</button>
                </div>
            </div>
            <!-- Controls Row -->
            <div class="flex flex-wrap items-center gap-3 mt-3">
                <div class="flex bg-gray-800 rounded-lg p-0.5" id="rangeSelector">
                    <button onclick="setRange('24h')" data-range="24h" class="range-btn px-3 py-1 rounded-md text-xs font-medium transition">24h</button>
                    <button onclick="setRange('7d')" data-range="7d" class="range-btn px-3 py-1 rounded-md text-xs font-medium transition bg-blue-600 text-white">7d</button>
                    <button onclick="setRange('30d')" data-range="30d" class="range-btn px-3 py-1 rounded-md text-xs font-medium transition">30d</button>
                </div>
                <button onclick="refreshAll()" class="flex items-center gap-1.5 bg-gray-800 hover:bg-gray-700 border border-gray-700 px-3 py-1.5 rounded-lg text-xs font-medium transition">
                    <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>
                    Refresh
                </button>
                <div class="flex items-center gap-2 ml-auto text-xs text-gray-500">
                    <span id="autoRefreshDot" class="status-dot dot-green animate-pulse-slow"></span>
                    <span>Auto-refresh 30s</span>
                    <span class="text-gray-600">|</span>
                    <span id="lastRefresh">Loading...</span>
                </div>
            </div>
        </div>
    </header>

    <main class="max-w-7xl mx-auto px-4 sm:px-6 py-6 space-y-6">

        <!-- Error Banner (hidden by default) -->
        <div id="errorBanner" class="hidden bg-red-900/50 border border-red-800 rounded-lg p-4 text-sm text-red-300">
            <strong>API Key Required:</strong> Enter your API key above to load dashboard data.
        </div>

        <!-- KPI Cards -->
        <div class="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <div class="card p-5">
                <p class="text-xs text-gray-400 uppercase tracking-wider font-medium">Total Face Records</p>
                <p class="text-3xl font-bold mt-2 text-white" id="kpiRecords">--</p>
                <div class="flex items-center gap-1.5 mt-2">
                    <span id="kpiIndexDot" class="status-dot dot-gray"></span>
                    <span id="kpiIndexLabel" class="text-xs text-gray-500">HNSW index: checking</span>
                </div>
            </div>
            <div class="card p-5">
                <p class="text-xs text-gray-400 uppercase tracking-wider font-medium">API Events</p>
                <p class="text-3xl font-bold mt-2 text-white" id="kpiEvents">--</p>
                <p class="text-xs text-gray-500 mt-2" id="kpiEventsRange">in selected period</p>
            </div>
            <div class="card p-5">
                <p class="text-xs text-gray-400 uppercase tracking-wider font-medium">Success Rate</p>
                <p class="text-3xl font-bold mt-2" id="kpiSuccessRate">--</p>
                <div class="w-full bg-gray-700 rounded-full h-1.5 mt-3">
                    <div id="kpiSuccessBar" class="bg-emerald-500 h-1.5 rounded-full transition-all duration-500" style="width: 0%"></div>
                </div>
            </div>
            <div class="card p-5">
                <p class="text-xs text-gray-400 uppercase tracking-wider font-medium">Avg Latency</p>
                <p class="text-3xl font-bold mt-2 text-white" id="kpiLatency">--</p>
                <p class="text-xs text-gray-500 mt-2">milliseconds</p>
            </div>
        </div>

        <!-- System Health -->
        <div class="card p-4">
            <div class="flex flex-wrap items-center gap-3">
                <span class="text-xs font-medium text-gray-400 uppercase tracking-wider mr-2">System Health</span>
                <span id="healthDB" class="pill pill-gray"><span class="status-dot dot-gray"></span>Database</span>
                <span id="healthRedis" class="pill pill-gray"><span class="status-dot dot-gray"></span>Redis</span>
                <span id="healthModel" class="pill pill-gray"><span class="status-dot dot-gray"></span>Face Model</span>
                <span id="healthGPU" class="pill pill-gray"><span class="status-dot dot-gray"></span>GPU</span>
                <span id="healthAntiSpoof" class="pill pill-gray"><span class="status-dot dot-gray"></span>Anti-Spoof</span>
            </div>
        </div>

        <!-- Charts Row 1 -->
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div class="card p-5">
                <h3 class="text-sm font-medium text-gray-300 mb-4">API Usage Trend</h3>
                <div style="height: 260px;"><canvas id="usageTrendChart"></canvas></div>
            </div>
            <div class="card p-5">
                <h3 class="text-sm font-medium text-gray-300 mb-4">Latency Trend</h3>
                <div style="height: 260px;"><canvas id="latencyTrendChart"></canvas></div>
            </div>
        </div>

        <!-- Charts Row 2 -->
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div class="card p-5">
                <h3 class="text-sm font-medium text-gray-300 mb-4">Event Type Breakdown</h3>
                <div style="height: 280px;" class="flex items-center justify-center"><canvas id="eventTypeChart"></canvas></div>
            </div>
            <div class="card p-5">
                <h3 class="text-sm font-medium text-gray-300 mb-4">Success vs Failure by Type</h3>
                <div style="height: 280px;"><canvas id="successFailChart"></canvas></div>
            </div>
        </div>

        <!-- Event Type Summary Table -->
        <div class="card overflow-hidden">
            <div class="p-5 border-b border-gray-700">
                <h3 class="text-sm font-medium text-gray-300">Event Type Summary</h3>
            </div>
            <div class="overflow-x-auto">
                <table class="w-full text-sm">
                    <thead>
                        <tr class="text-left text-xs text-gray-400 uppercase tracking-wider border-b border-gray-700">
                            <th class="px-5 py-3 font-medium">Event Type</th>
                            <th class="px-5 py-3 font-medium text-right">Total</th>
                            <th class="px-5 py-3 font-medium text-right">Success</th>
                            <th class="px-5 py-3 font-medium text-right">Failed</th>
                            <th class="px-5 py-3 font-medium text-right">Error</th>
                            <th class="px-5 py-3 font-medium text-right">Success Rate</th>
                            <th class="px-5 py-3 font-medium text-right">Avg Latency</th>
                        </tr>
                    </thead>
                    <tbody id="summaryTableBody" class="divide-y divide-gray-800">
                        <tr><td colspan="7" class="px-5 py-8 text-center text-gray-500">Loading data...</td></tr>
                    </tbody>
                </table>
            </div>
        </div>

        <!-- Recent Events -->
        <div class="card overflow-hidden">
            <div class="p-5 border-b border-gray-700 flex items-center justify-between">
                <h3 class="text-sm font-medium text-gray-300">Recent Events</h3>
                <div class="flex gap-2">
                    <select id="eventTypeFilter" onchange="refreshEvents()" class="bg-gray-800 border border-gray-700 rounded-lg px-2 py-1 text-xs text-gray-300 outline-none">
                        <option value="">All Types</option>
                        <option value="enroll">enroll</option>
                        <option value="match">match</option>
                        <option value="deduplicate">deduplicate</option>
                        <option value="compare">compare</option>
                        <option value="liveness">liveness</option>
                        <option value="multi_frame_liveness">multi_frame_liveness</option>
                        <option value="record_get">record_get</option>
                        <option value="record_delete">record_delete</option>
                        <option value="batch_enroll">batch_enroll</option>
                        <option value="batch_enroll_embeddings">batch_enroll_embeddings</option>
                    </select>
                    <select id="statusFilter" onchange="refreshEvents()" class="bg-gray-800 border border-gray-700 rounded-lg px-2 py-1 text-xs text-gray-300 outline-none">
                        <option value="">All Statuses</option>
                        <option value="success">success</option>
                        <option value="failed">failed</option>
                        <option value="error">error</option>
                    </select>
                </div>
            </div>
            <div class="overflow-x-auto" style="max-height: 440px; overflow-y: auto;">
                <table class="w-full text-sm">
                    <thead class="table-header">
                        <tr class="text-left text-xs text-gray-400 uppercase tracking-wider border-b border-gray-700">
                            <th class="px-5 py-3 font-medium">Time</th>
                            <th class="px-5 py-3 font-medium">Type</th>
                            <th class="px-5 py-3 font-medium">Status</th>
                            <th class="px-5 py-3 font-medium text-right">Duration</th>
                            <th class="px-5 py-3 font-medium">Record ID</th>
                            <th class="px-5 py-3 font-medium">Details</th>
                        </tr>
                    </thead>
                    <tbody id="eventsTableBody" class="divide-y divide-gray-800">
                        <tr><td colspan="6" class="px-5 py-8 text-center text-gray-500">Loading events...</td></tr>
                    </tbody>
                </table>
            </div>
        </div>

    </main>

    <!-- Footer -->
    <footer class="border-t border-gray-800 mt-8">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 py-4 flex flex-wrap items-center justify-between text-xs text-gray-500">
            <span>FaceDedup Dashboard &mdash; Monitoring &amp; Analytics</span>
            <span>Data refreshes automatically every 30 seconds</span>
        </div>
    </footer>

<script>
// ===== State =====
let currentRange = '7d';
let refreshInterval = null;
const REFRESH_MS = 30000;

// Chart instances
let usageTrendChart = null;
let latencyTrendChart = null;
let eventTypeChart = null;
let successFailChart = null;

// Color palette for event types
const TYPE_COLORS = {
    enroll: '#3b82f6',
    match: '#10b981',
    deduplicate: '#f59e0b',
    compare: '#8b5cf6',
    liveness: '#ec4899',
    multi_frame_liveness: '#f97316',
    record_get: '#06b6d4',
    record_delete: '#ef4444',
    batch_enroll: '#14b8a6',
    batch_enroll_embeddings: '#a855f7',
};

const STATUS_COLORS = {
    success: '#10b981',
    failed: '#f59e0b',
    error: '#ef4444',
};

// ===== Init =====
document.addEventListener('DOMContentLoaded', () => {
    const saved = sessionStorage.getItem('facededup_dashboard_key');
    if (saved) document.getElementById('apiKey').value = saved;
    initCharts();
    refreshAll();
    startAutoRefresh();
});

// ===== API Key =====
function saveKey() {
    const key = document.getElementById('apiKey').value.trim();
    if (key) {
        sessionStorage.setItem('facededup_dashboard_key', key);
        refreshAll();
    }
}

function toggleKeyVis() {
    const inp = document.getElementById('apiKey');
    const btn = document.getElementById('keyToggleBtn');
    if (inp.type === 'password') { inp.type = 'text'; btn.textContent = 'hide'; }
    else { inp.type = 'password'; btn.textContent = 'show'; }
}

// ===== Date Range =====
function setRange(range) {
    currentRange = range;
    document.querySelectorAll('.range-btn').forEach(b => {
        b.classList.remove('bg-blue-600', 'text-white');
        b.classList.add('text-gray-400', 'hover:text-white');
    });
    const active = document.querySelector(`[data-range="${range}"]`);
    if (active) {
        active.classList.add('bg-blue-600', 'text-white');
        active.classList.remove('text-gray-400', 'hover:text-white');
    }
    refreshAll();
}

function getDateRange() {
    const now = new Date();
    let start;
    switch (currentRange) {
        case '24h': start = new Date(now.getTime() - 24 * 60 * 60 * 1000); break;
        case '7d':  start = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000); break;
        case '30d': start = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000); break;
        default:    start = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
    }
    return { start: start.toISOString(), end: now.toISOString() };
}

// ===== Auto Refresh =====
function startAutoRefresh() {
    if (refreshInterval) clearInterval(refreshInterval);
    refreshInterval = setInterval(refreshAll, REFRESH_MS);
}

document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
        if (refreshInterval) { clearInterval(refreshInterval); refreshInterval = null; }
    } else {
        refreshAll();
        startAutoRefresh();
    }
});

// ===== API Helper =====
async function dashApi(method, path, query = {}) {
    const baseUrl = window.location.origin + '/api/v1';
    const apiKey = document.getElementById('apiKey').value.trim();
    const url = new URL(baseUrl + path);
    for (const [k, v] of Object.entries(query)) {
        if (v !== null && v !== undefined && v !== '') url.searchParams.append(k, v);
    }
    const headers = {};
    if (apiKey) headers['X-API-Key'] = apiKey;
    const resp = await fetch(url, { method, headers });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    return resp.json();
}

// ===== Main Refresh =====
async function refreshAll() {
    const apiKey = document.getElementById('apiKey').value.trim();
    const banner = document.getElementById('errorBanner');
    if (!apiKey) {
        banner.classList.remove('hidden');
        return;
    }
    banner.classList.add('hidden');

    const { start, end } = getDateRange();
    const tsInterval = currentRange === '24h' ? 'hour' : 'day';

    const [health, summary, timeseries, indexStatus, recentEvents] = await Promise.allSettled([
        dashApi('GET', '/health'),
        dashApi('GET', '/analytics/summary', { start, end }),
        dashApi('GET', '/analytics/timeseries', { start, end, interval: tsInterval }),
        dashApi('GET', '/admin/index/status'),
        dashApi('GET', '/analytics/events', { limit: 25 }),
    ]);

    if (health.status === 'fulfilled') renderHealth(health.value);
    if (summary.status === 'fulfilled') renderSummary(summary.value);
    if (timeseries.status === 'fulfilled') renderTimeseries(timeseries.value);
    if (indexStatus.status === 'fulfilled') renderIndexStatus(indexStatus.value);
    if (recentEvents.status === 'fulfilled') renderRecentEvents(recentEvents.value);

    document.getElementById('lastRefresh').textContent = 'Last refresh: ' + new Date().toLocaleTimeString();
}

async function refreshEvents() {
    const apiKey = document.getElementById('apiKey').value.trim();
    if (!apiKey) return;
    const evtType = document.getElementById('eventTypeFilter').value;
    const status = document.getElementById('statusFilter').value;
    try {
        const data = await dashApi('GET', '/analytics/events', { event_type: evtType, status: status, limit: 25 });
        renderRecentEvents(data);
    } catch (e) { /* ignore */ }
}

// ===== Render Functions =====

function renderHealth(data) {
    setHealthPill('healthDB', data.database === 'connected', data.database === 'connected' ? 'Database' : 'DB Down');
    setHealthPill('healthRedis', data.redis === 'connected', data.redis === 'connected' ? 'Redis' : 'Redis Down');
    setHealthPill('healthModel', data.face_model_loaded, data.face_model_loaded ? 'Face Model' : 'Model Missing');
    setHealthPill('healthGPU', data.gpu_enabled, data.gpu_enabled ? 'GPU Active' : 'CPU Only');
    setHealthPill('healthAntiSpoof', data.anti_spoof_loaded, data.anti_spoof_loaded ? 'Anti-Spoof' : 'No Anti-Spoof');
}

function setHealthPill(id, ok, label) {
    const el = document.getElementById(id);
    const dotClass = ok ? 'dot-green' : (ok === false ? 'dot-red' : 'dot-gray');
    const pillClass = ok ? 'pill-green' : (ok === false ? 'pill-red' : 'pill-gray');
    el.className = 'pill ' + pillClass;
    el.innerHTML = '<span class="status-dot ' + dotClass + '"></span>' + label;
}

function renderIndexStatus(data) {
    document.getElementById('kpiRecords').textContent = Number(data.total_records).toLocaleString();
    const dot = document.getElementById('kpiIndexDot');
    const label = document.getElementById('kpiIndexLabel');
    if (data.index_exists) {
        dot.className = 'status-dot dot-green';
        label.textContent = 'HNSW index: active';
        label.className = 'text-xs text-emerald-400';
    } else {
        dot.className = 'status-dot dot-yellow';
        label.textContent = 'HNSW index: not built';
        label.className = 'text-xs text-amber-400';
    }
}

function renderSummary(data) {
    document.getElementById('kpiEvents').textContent = Number(data.total_events).toLocaleString();
    document.getElementById('kpiEventsRange').textContent = 'in last ' + currentRange;

    // Success rate
    let totalSuccess = 0, totalAll = 0;
    let totalDuration = 0, durationCount = 0;
    for (const t of data.by_type) {
        totalSuccess += t.success;
        totalAll += t.total;
        if (t.avg_duration_ms) { totalDuration += t.avg_duration_ms * t.total; durationCount += t.total; }
    }
    const rate = totalAll > 0 ? (totalSuccess / totalAll * 100) : 0;
    const rateEl = document.getElementById('kpiSuccessRate');
    rateEl.textContent = rate.toFixed(1) + '%';
    rateEl.className = 'text-3xl font-bold mt-2 ' + (rate >= 95 ? 'text-emerald-400' : rate >= 85 ? 'text-amber-400' : 'text-red-400');
    document.getElementById('kpiSuccessBar').style.width = rate + '%';

    // Avg latency
    const avgMs = durationCount > 0 ? (totalDuration / durationCount) : 0;
    document.getElementById('kpiLatency').textContent = avgMs > 0 ? Math.round(avgMs).toLocaleString() : '--';

    // Summary table
    renderSummaryTable(data.by_type);

    // Doughnut chart
    updateEventTypeChart(data.by_type);

    // Stacked bar chart
    updateSuccessFailChart(data.by_type);
}

function renderSummaryTable(byType) {
    const tbody = document.getElementById('summaryTableBody');
    if (!byType.length) {
        tbody.innerHTML = '<tr><td colspan="7" class="px-5 py-8 text-center text-gray-500">No events recorded yet</td></tr>';
        return;
    }
    tbody.innerHTML = byType.map(t => {
        const rate = t.total > 0 ? (t.success / t.total * 100) : 0;
        const rateClass = rate >= 95 ? 'badge-success' : rate >= 85 ? 'badge-failed' : 'badge-error';
        const color = TYPE_COLORS[t.event_type] || '#6b7280';
        return `<tr class="event-row transition">
            <td class="px-5 py-3 font-medium">
                <span class="inline-block w-2.5 h-2.5 rounded-full mr-2" style="background:${color}"></span>
                ${t.event_type}
            </td>
            <td class="px-5 py-3 text-right text-gray-300">${t.total.toLocaleString()}</td>
            <td class="px-5 py-3 text-right text-emerald-400">${t.success.toLocaleString()}</td>
            <td class="px-5 py-3 text-right text-amber-400">${t.failed.toLocaleString()}</td>
            <td class="px-5 py-3 text-right text-red-400">${t.error.toLocaleString()}</td>
            <td class="px-5 py-3 text-right"><span class="badge ${rateClass}">${rate.toFixed(1)}%</span></td>
            <td class="px-5 py-3 text-right text-gray-300">${t.avg_duration_ms ? Math.round(t.avg_duration_ms) + 'ms' : '--'}</td>
        </tr>`;
    }).join('');
}

function renderRecentEvents(data) {
    const tbody = document.getElementById('eventsTableBody');
    if (!data.events || !data.events.length) {
        tbody.innerHTML = '<tr><td colspan="6" class="px-5 py-8 text-center text-gray-500">No events found</td></tr>';
        return;
    }
    tbody.innerHTML = data.events.map(e => {
        const time = timeAgo(new Date(e.created_at));
        const badgeClass = e.status === 'success' ? 'badge-success' : e.status === 'failed' ? 'badge-failed' : 'badge-error';
        const recId = e.record_id ? e.record_id.substring(0, 8) + '...' : '--';
        const detail = e.error_detail ? e.error_detail.substring(0, 60) + (e.error_detail.length > 60 ? '...' : '') : (e.metadata ? summarizeMetadata(e.metadata) : '--');
        return `<tr class="event-row transition">
            <td class="px-5 py-2.5 text-gray-400 whitespace-nowrap" title="${new Date(e.created_at).toLocaleString()}">${time}</td>
            <td class="px-5 py-2.5">
                <span class="inline-block w-2 h-2 rounded-full mr-1.5" style="background:${TYPE_COLORS[e.event_type] || '#6b7280'}"></span>
                ${e.event_type}
            </td>
            <td class="px-5 py-2.5"><span class="badge ${badgeClass}">${e.status}</span></td>
            <td class="px-5 py-2.5 text-right text-gray-300">${e.duration_ms ? e.duration_ms + 'ms' : '--'}</td>
            <td class="px-5 py-2.5 font-mono text-xs text-gray-400">${recId}</td>
            <td class="px-5 py-2.5 text-xs text-gray-500 max-w-xs truncate">${detail}</td>
        </tr>`;
    }).join('');
}

function summarizeMetadata(meta) {
    if (!meta || typeof meta !== 'object') return '--';
    const parts = [];
    if (meta.match_count !== undefined) parts.push('matches: ' + meta.match_count);
    if (meta.similarity !== undefined) parts.push('sim: ' + Number(meta.similarity).toFixed(2));
    if (meta.is_live !== undefined) parts.push(meta.is_live ? 'live' : 'spoof');
    if (meta.has_duplicates !== undefined) parts.push(meta.has_duplicates ? 'dup found' : 'unique');
    if (meta.total_success !== undefined) parts.push('ok: ' + meta.total_success);
    if (meta.total_failed !== undefined) parts.push('fail: ' + meta.total_failed);
    return parts.length > 0 ? parts.join(', ') : '--';
}

function timeAgo(date) {
    const seconds = Math.floor((new Date() - date) / 1000);
    if (seconds < 60) return seconds + 's ago';
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return minutes + 'm ago';
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return hours + 'h ago';
    const days = Math.floor(hours / 24);
    return days + 'd ago';
}

// ===== Chart Init =====
function initCharts() {
    Chart.defaults.color = '#9ca3af';
    Chart.defaults.borderColor = '#374151';

    // Usage Trend (Line)
    const usageCtx = document.getElementById('usageTrendChart').getContext('2d');
    usageTrendChart = new Chart(usageCtx, {
        type: 'line',
        data: { labels: [], datasets: [
            { label: 'Total', data: [], borderColor: '#3b82f6', backgroundColor: 'rgba(59,130,246,0.1)', fill: true, tension: 0.3, pointRadius: 2 },
            { label: 'Success', data: [], borderColor: '#10b981', backgroundColor: 'transparent', borderDash: [4,2], tension: 0.3, pointRadius: 0 },
            { label: 'Failed', data: [], borderColor: '#f59e0b', backgroundColor: 'transparent', borderDash: [4,2], tension: 0.3, pointRadius: 0 },
        ]},
        options: {
            responsive: true, maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: { legend: { display: true, position: 'top', labels: { boxWidth: 12, padding: 15, font: { size: 11 } } } },
            scales: {
                x: { grid: { display: false }, ticks: { font: { size: 10 }, maxRotation: 0 } },
                y: { beginAtZero: true, grid: { color: '#1f2937' }, ticks: { font: { size: 10 } } },
            },
        },
    });

    // Latency Trend (Line)
    const latencyCtx = document.getElementById('latencyTrendChart').getContext('2d');
    latencyTrendChart = new Chart(latencyCtx, {
        type: 'line',
        data: { labels: [], datasets: [
            { label: 'Avg Latency (ms)', data: [], borderColor: '#f59e0b', backgroundColor: 'rgba(245,158,11,0.1)', fill: true, tension: 0.3, pointRadius: 2 },
        ]},
        options: {
            responsive: true, maintainAspectRatio: false,
            plugins: { legend: { display: true, position: 'top', labels: { boxWidth: 12, padding: 15, font: { size: 11 } } } },
            scales: {
                x: { grid: { display: false }, ticks: { font: { size: 10 }, maxRotation: 0 } },
                y: { beginAtZero: true, grid: { color: '#1f2937' }, ticks: { font: { size: 10 }, callback: v => v + 'ms' } },
            },
        },
    });

    // Event Type Breakdown (Doughnut)
    const typeCtx = document.getElementById('eventTypeChart').getContext('2d');
    eventTypeChart = new Chart(typeCtx, {
        type: 'doughnut',
        data: { labels: [], datasets: [{ data: [], backgroundColor: [], borderWidth: 0 }] },
        options: {
            responsive: true, maintainAspectRatio: false,
            cutout: '65%',
            plugins: {
                legend: { display: true, position: 'right', labels: { boxWidth: 10, padding: 8, font: { size: 11 }, color: '#9ca3af' } },
            },
        },
    });

    // Success vs Failure (Stacked Bar)
    const sfCtx = document.getElementById('successFailChart').getContext('2d');
    successFailChart = new Chart(sfCtx, {
        type: 'bar',
        data: { labels: [], datasets: [
            { label: 'Success', data: [], backgroundColor: '#10b981' },
            { label: 'Failed', data: [], backgroundColor: '#f59e0b' },
            { label: 'Error', data: [], backgroundColor: '#ef4444' },
        ]},
        options: {
            responsive: true, maintainAspectRatio: false,
            plugins: { legend: { display: true, position: 'top', labels: { boxWidth: 12, padding: 15, font: { size: 11 } } } },
            scales: {
                x: { stacked: true, grid: { display: false }, ticks: { font: { size: 10 }, maxRotation: 45 } },
                y: { stacked: true, beginAtZero: true, grid: { color: '#1f2937' }, ticks: { font: { size: 10 } } },
            },
        },
    });
}

// ===== Chart Updates =====

function renderTimeseries(data) {
    if (!data.buckets || !data.buckets.length) {
        usageTrendChart.data.labels = [];
        usageTrendChart.data.datasets.forEach(ds => ds.data = []);
        usageTrendChart.update();
        latencyTrendChart.data.labels = [];
        latencyTrendChart.data.datasets[0].data = [];
        latencyTrendChart.update();
        return;
    }

    const labels = data.buckets.map(b => {
        const d = new Date(b.timestamp);
        if (data.interval === 'hour') return d.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
        return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
    });

    // Usage trend
    usageTrendChart.data.labels = labels;
    usageTrendChart.data.datasets[0].data = data.buckets.map(b => b.total);
    usageTrendChart.data.datasets[1].data = data.buckets.map(b => b.success);
    usageTrendChart.data.datasets[2].data = data.buckets.map(b => b.failed + b.error);
    usageTrendChart.update();

    // Latency trend
    latencyTrendChart.data.labels = labels;
    latencyTrendChart.data.datasets[0].data = data.buckets.map(b => b.avg_duration_ms || 0);
    latencyTrendChart.update();
}

function updateEventTypeChart(byType) {
    if (!byType.length) {
        eventTypeChart.data.labels = [];
        eventTypeChart.data.datasets[0].data = [];
        eventTypeChart.data.datasets[0].backgroundColor = [];
        eventTypeChart.update();
        return;
    }
    eventTypeChart.data.labels = byType.map(t => t.event_type);
    eventTypeChart.data.datasets[0].data = byType.map(t => t.total);
    eventTypeChart.data.datasets[0].backgroundColor = byType.map(t => TYPE_COLORS[t.event_type] || '#6b7280');
    eventTypeChart.update();
}

function updateSuccessFailChart(byType) {
    if (!byType.length) {
        successFailChart.data.labels = [];
        successFailChart.data.datasets.forEach(ds => ds.data = []);
        successFailChart.update();
        return;
    }
    successFailChart.data.labels = byType.map(t => t.event_type);
    successFailChart.data.datasets[0].data = byType.map(t => t.success);
    successFailChart.data.datasets[1].data = byType.map(t => t.failed);
    successFailChart.data.datasets[2].data = byType.map(t => t.error);
    successFailChart.update();
}

// ===== Keyboard shortcut: Enter to save key =====
document.getElementById('apiKey').addEventListener('keydown', e => {
    if (e.key === 'Enter') saveKey();
});
</script>

</body>
</html>"""
