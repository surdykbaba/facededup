def get_events_html() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>FaceDedup &mdash; API Events</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        body { font-family: 'Inter', system-ui, -apple-system, sans-serif; }
        .card { background: #1f2937; border-radius: 12px; border: 1px solid #374151; }
        .pill { display: inline-flex; align-items: center; gap: 6px; padding: 4px 12px; border-radius: 9999px; font-size: 12px; font-weight: 500; }
        .pill-green { background: #064e3b; color: #6ee7b7; }
        .pill-red { background: #7f1d1d; color: #fca5a5; }
        .pill-yellow { background: #78350f; color: #fde68a; }
        .pill-gray { background: #374151; color: #9ca3af; }
        .badge { padding: 2px 8px; border-radius: 6px; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; }
        .badge-success { background: #064e3b; color: #6ee7b7; }
        .badge-failed { background: #78350f; color: #fde68a; }
        .badge-error { background: #7f1d1d; color: #fca5a5; }
        .event-row { cursor: pointer; }
        .event-row:hover { background: #1f2937; }
        .event-row:active { background: #374151; }
        .table-header { position: sticky; top: 0; background: #111827; z-index: 10; }
        ::-webkit-scrollbar { width: 6px; height: 6px; }
        ::-webkit-scrollbar-track { background: #1f2937; }
        ::-webkit-scrollbar-thumb { background: #4b5563; border-radius: 3px; }
        /* Modal styles */
        .detail-grid { display: grid; grid-template-columns: 140px 1fr; gap: 8px 16px; align-items: start; }
        .detail-label { color: #9ca3af; font-size: 12px; font-weight: 500; text-transform: uppercase; letter-spacing: 0.05em; padding-top: 2px; }
        .detail-value { color: #e5e7eb; font-size: 14px; word-break: break-all; }
        .error-box { background: #7f1d1d; border: 1px solid #991b1b; border-radius: 8px; padding: 12px; font-family: monospace; font-size: 13px; color: #fca5a5; white-space: pre-wrap; max-height: 200px; overflow-y: auto; }
        .metadata-box { background: #111827; border: 1px solid #374151; border-radius: 8px; padding: 12px; font-family: monospace; font-size: 13px; color: #d1d5db; white-space: pre-wrap; max-height: 200px; overflow-y: auto; }
        .face-image { max-width: 280px; max-height: 280px; border-radius: 8px; border: 1px solid #374151; }
        .pagination-btn { background: #1f2937; border: 1px solid #374151; border-radius: 6px; padding: 4px 10px; font-size: 12px; color: #9ca3af; cursor: pointer; transition: all 0.15s; }
        .pagination-btn:hover:not(:disabled) { background: #374151; color: #e5e7eb; }
        .pagination-btn:disabled { opacity: 0.3; cursor: not-allowed; }
        .spinner { border: 3px solid #374151; border-top: 3px solid #3b82f6; border-radius: 50%; width: 20px; height: 20px; animation: spin 0.8s linear infinite; display: inline-block; }
        @keyframes spin { to { transform: rotate(360deg); } }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
        .animate-pulse-slow { animation: pulse 2s ease-in-out infinite; }
        .status-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
        .dot-green { background: #10b981; }
        .dot-gray { background: #6b7280; }
    </style>
</head>
<body class="bg-gray-900 text-gray-100 min-h-screen">

    <!-- Header -->
    <header class="bg-gray-950 border-b border-gray-800">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 py-4">
            <div class="flex flex-wrap items-center justify-between gap-4">
                <div class="flex items-center gap-3">
                    <div class="w-8 h-8 bg-indigo-600 rounded-lg flex items-center justify-center">
                        <svg class="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01"/>
                        </svg>
                    </div>
                    <div>
                        <h1 class="text-xl font-bold text-white">API Events</h1>
                        <p class="text-xs text-gray-500">Full event log &amp; details</p>
                    </div>
                </div>
                <div class="flex flex-wrap items-center gap-3">
                    <a href="/dashboard" class="text-sm text-gray-400 hover:text-white transition">&#8592; Dashboard</a>
                    <div class="h-4 w-px bg-gray-700"></div>
                    <div class="relative">
                        <input type="password" id="apiKey" placeholder="X-API-Key"
                            class="bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm font-mono text-gray-300 w-48 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none pr-12">
                        <button onclick="toggleKeyVis()" id="keyToggleBtn" class="absolute right-2 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300 text-xs">show</button>
                    </div>
                    <button onclick="saveKey()" class="bg-blue-600 hover:bg-blue-700 text-white px-3 py-1.5 rounded-lg text-sm font-medium transition">Save</button>
                </div>
            </div>
            <!-- Filters Row -->
            <div class="flex flex-wrap items-center gap-3 mt-3">
                <select id="eventTypeFilter" onchange="resetAndRefresh()" class="bg-gray-800 border border-gray-700 rounded-lg px-2.5 py-1.5 text-xs text-gray-300 outline-none">
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
                <select id="statusFilter" onchange="resetAndRefresh()" class="bg-gray-800 border border-gray-700 rounded-lg px-2.5 py-1.5 text-xs text-gray-300 outline-none">
                    <option value="">All Statuses</option>
                    <option value="success">success</option>
                    <option value="failed">failed</option>
                    <option value="error">error</option>
                </select>
                <div class="flex items-center gap-1.5">
                    <label class="text-xs text-gray-500">From</label>
                    <input type="date" id="dateStart" onchange="resetAndRefresh()" class="bg-gray-800 border border-gray-700 rounded-lg px-2 py-1 text-xs text-gray-300 outline-none">
                </div>
                <div class="flex items-center gap-1.5">
                    <label class="text-xs text-gray-500">To</label>
                    <input type="date" id="dateEnd" onchange="resetAndRefresh()" class="bg-gray-800 border border-gray-700 rounded-lg px-2 py-1 text-xs text-gray-300 outline-none">
                </div>
                <button onclick="clearFilters()" class="text-xs text-gray-500 hover:text-gray-300 transition underline">Clear filters</button>
                <div class="flex items-center gap-2 ml-auto text-xs text-gray-500">
                    <span class="status-dot dot-green animate-pulse-slow"></span>
                    <span>Auto-refresh 60s</span>
                    <span class="text-gray-600">|</span>
                    <span id="lastRefresh">Loading...</span>
                </div>
            </div>
        </div>
    </header>

    <main class="max-w-7xl mx-auto px-4 sm:px-6 py-6 space-y-4">

        <!-- Error Banner -->
        <div id="errorBanner" class="hidden bg-red-900/50 border border-red-800 rounded-lg p-4 text-sm text-red-300">
            <strong>API Key Required:</strong> Enter your API key above to load events data.
        </div>

        <!-- API Error Banner -->
        <div id="apiErrorBanner" class="hidden bg-amber-900/50 border border-amber-800 rounded-lg p-4 text-sm text-amber-200">
            <div class="flex items-start gap-2">
                <svg class="w-5 h-5 text-amber-400 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z"/>
                </svg>
                <div>
                    <strong>Error loading events:</strong>
                    <span id="apiErrorMsg" class="text-amber-300/80"></span>
                </div>
            </div>
        </div>

        <!-- Events Table -->
        <div class="card overflow-hidden">
            <div class="p-5 border-b border-gray-700">
                <div class="flex flex-wrap items-center justify-between gap-2">
                    <div class="flex items-center gap-3">
                        <h3 class="text-sm font-medium text-gray-300">Events</h3>
                        <span id="eventsTotal" class="text-xs text-gray-500">-- events</span>
                    </div>
                    <div class="flex items-center gap-2">
                        <select id="pageSizeSelect" onchange="changePageSize()" class="bg-gray-800 border border-gray-700 rounded-lg px-2 py-1 text-xs text-gray-300 outline-none">
                            <option value="10">10 / page</option>
                            <option value="25" selected>25 / page</option>
                            <option value="50">50 / page</option>
                            <option value="100">100 / page</option>
                        </select>
                        <div class="flex items-center gap-1">
                            <button id="prevPageBtn" onclick="prevPage()" disabled class="pagination-btn">&#8592; Prev</button>
                            <span id="pageInfo" class="text-xs text-gray-500 px-2 whitespace-nowrap">Page 1</span>
                            <button id="nextPageBtn" onclick="nextPage()" disabled class="pagination-btn">Next &#8594;</button>
                        </div>
                    </div>
                </div>
            </div>
            <div class="overflow-x-auto">
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
            <!-- Bottom pagination row -->
            <div class="p-4 border-t border-gray-700 flex items-center justify-between">
                <span id="eventsTotal2" class="text-xs text-gray-500">-- events</span>
                <div class="flex items-center gap-2">
                    <button id="prevPageBtn2" onclick="prevPage()" disabled class="pagination-btn">&#8592; Prev</button>
                    <span id="pageInfo2" class="text-xs text-gray-500 px-2 whitespace-nowrap">Page 1</span>
                    <button id="nextPageBtn2" onclick="nextPage()" disabled class="pagination-btn">Next &#8594;</button>
                </div>
            </div>
        </div>

    </main>

    <!-- Event Detail Modal -->
    <div id="eventModal" class="fixed inset-0 z-50 hidden" style="backdrop-filter: blur(2px);">
        <div class="absolute inset-0 bg-black/60" onclick="closeModal()"></div>
        <div class="absolute inset-4 sm:inset-8 lg:inset-y-8 lg:inset-x-[15%] bg-gray-900 border border-gray-700 rounded-xl shadow-2xl overflow-hidden flex flex-col">
            <div class="flex items-center justify-between p-5 border-b border-gray-700 flex-shrink-0">
                <h3 id="modalTitle" class="text-sm font-medium text-gray-300">Event Detail</h3>
                <button onclick="closeModal()" class="text-gray-400 hover:text-white text-xl leading-none px-2">&times;</button>
            </div>
            <div id="modalContent" class="flex-1 overflow-y-auto p-5 space-y-5">
                <!-- Populated dynamically -->
            </div>
        </div>
    </div>

    <!-- Footer -->
    <footer class="border-t border-gray-800 mt-8">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 py-4 flex flex-wrap items-center justify-between text-xs text-gray-500">
            <span>FaceDedup &mdash; API Events Log</span>
            <span>Data refreshes automatically every 60 seconds</span>
        </div>
    </footer>

<script>
// ===== State =====
let currentPage = 1;
let currentPageSize = 25;
let totalEvents = 0;
let currentEventsData = [];
let refreshInterval = null;
const REFRESH_MS = 60000;

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

// ===== Init =====
document.addEventListener('DOMContentLoaded', () => {
    const saved = sessionStorage.getItem('facededup_dashboard_key');
    if (saved) document.getElementById('apiKey').value = saved;
    refreshEvents();
    startAutoRefresh();
});

// ===== API Key =====
function saveKey() {
    const key = document.getElementById('apiKey').value.trim();
    if (key) {
        sessionStorage.setItem('facededup_dashboard_key', key);
        refreshEvents();
    }
}

function toggleKeyVis() {
    const inp = document.getElementById('apiKey');
    const btn = document.getElementById('keyToggleBtn');
    if (inp.type === 'password') { inp.type = 'text'; btn.textContent = 'hide'; }
    else { inp.type = 'password'; btn.textContent = 'show'; }
}

document.getElementById('apiKey').addEventListener('keydown', e => {
    if (e.key === 'Enter') saveKey();
});

// ===== Auto Refresh =====
function startAutoRefresh() {
    if (refreshInterval) clearInterval(refreshInterval);
    refreshInterval = setInterval(refreshEvents, REFRESH_MS);
}

document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
        if (refreshInterval) { clearInterval(refreshInterval); refreshInterval = null; }
    } else {
        refreshEvents();
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
    if (!resp.ok) {
        let detail = 'HTTP ' + resp.status;
        try { const body = await resp.json(); detail += ': ' + (body.detail || JSON.stringify(body)); } catch {}
        if (resp.status === 401) detail = 'Unauthorized - check your API key';
        if (resp.status === 403) detail = 'Forbidden - API key is invalid';
        throw new Error(detail);
    }
    return resp.json();
}

// ===== Filters & Pagination =====
function resetAndRefresh() {
    currentPage = 1;
    refreshEvents();
}

function changePageSize() {
    currentPageSize = parseInt(document.getElementById('pageSizeSelect').value, 10);
    currentPage = 1;
    refreshEvents();
}

function prevPage() {
    if (currentPage > 1) { currentPage--; refreshEvents(); }
}

function nextPage() {
    const totalPages = Math.max(1, Math.ceil(totalEvents / currentPageSize));
    if (currentPage < totalPages) { currentPage++; refreshEvents(); }
}

function clearFilters() {
    document.getElementById('eventTypeFilter').value = '';
    document.getElementById('statusFilter').value = '';
    document.getElementById('dateStart').value = '';
    document.getElementById('dateEnd').value = '';
    resetAndRefresh();
}

// ===== Main Data Fetch =====
async function refreshEvents() {
    const apiKey = document.getElementById('apiKey').value.trim();
    const banner = document.getElementById('errorBanner');
    const apiBanner = document.getElementById('apiErrorBanner');
    if (!apiKey) {
        banner.classList.remove('hidden');
        apiBanner.classList.add('hidden');
        return;
    }
    banner.classList.add('hidden');

    const evtType = document.getElementById('eventTypeFilter').value;
    const status = document.getElementById('statusFilter').value;
    const dateStart = document.getElementById('dateStart').value;
    const dateEnd = document.getElementById('dateEnd').value;
    const offset = (currentPage - 1) * currentPageSize;

    const query = { offset, limit: currentPageSize };
    if (evtType) query.event_type = evtType;
    if (status) query.status = status;
    if (dateStart) query.start = new Date(dateStart).toISOString();
    if (dateEnd) {
        const end = new Date(dateEnd);
        end.setHours(23, 59, 59, 999);
        query.end = end.toISOString();
    }

    try {
        const data = await dashApi('GET', '/analytics/events', query);
        apiBanner.classList.add('hidden');
        renderEvents(data);
    } catch (e) {
        console.error('[Events] refreshEvents failed:', e.message);
        document.getElementById('apiErrorMsg').textContent = e.message;
        apiBanner.classList.remove('hidden');
    }

    document.getElementById('lastRefresh').textContent = 'Last refresh: ' + new Date().toLocaleTimeString();
}

// ===== Render =====
function renderEvents(data) {
    const tbody = document.getElementById('eventsTableBody');
    totalEvents = data.total || 0;
    currentEventsData = data.events || [];

    // Update pagination display (top & bottom)
    const totalPages = Math.max(1, Math.ceil(totalEvents / currentPageSize));
    const totalText = totalEvents.toLocaleString() + ' events';
    const pageText = 'Page ' + currentPage + ' of ' + totalPages;
    const atFirst = (currentPage <= 1);
    const atLast = (currentPage >= totalPages);

    document.getElementById('eventsTotal').textContent = totalText;
    document.getElementById('eventsTotal2').textContent = totalText;
    document.getElementById('pageInfo').textContent = pageText;
    document.getElementById('pageInfo2').textContent = pageText;
    document.getElementById('prevPageBtn').disabled = atFirst;
    document.getElementById('prevPageBtn2').disabled = atFirst;
    document.getElementById('nextPageBtn').disabled = atLast;
    document.getElementById('nextPageBtn2').disabled = atLast;

    if (!currentEventsData.length) {
        tbody.innerHTML = '<tr><td colspan="6" class="px-5 py-8 text-center text-gray-500">No events found</td></tr>';
        return;
    }

    tbody.innerHTML = currentEventsData.map((e, idx) => {
        const time = timeAgo(new Date(e.created_at));
        const badgeClass = e.status === 'success' ? 'badge-success' : e.status === 'failed' ? 'badge-failed' : 'badge-error';
        const recId = e.record_id ? e.record_id.substring(0, 8) + '...' : '--';
        const detail = e.error_detail
            ? e.error_detail.substring(0, 60) + (e.error_detail.length > 60 ? '...' : '')
            : (e.metadata ? summarizeMetadata(e.metadata) : '--');
        return '<tr class="event-row transition" onclick="openEventDetail(' + idx + ')">' +
            '<td class="px-5 py-2.5 text-gray-400 whitespace-nowrap" title="' + new Date(e.created_at).toLocaleString() + '">' + time + '</td>' +
            '<td class="px-5 py-2.5"><span class="inline-block w-2 h-2 rounded-full mr-1.5" style="background:' + (TYPE_COLORS[e.event_type] || '#6b7280') + '"></span>' + e.event_type + '</td>' +
            '<td class="px-5 py-2.5"><span class="badge ' + badgeClass + '">' + e.status + '</span></td>' +
            '<td class="px-5 py-2.5 text-right text-gray-300">' + (e.duration_ms ? e.duration_ms + 'ms' : '--') + '</td>' +
            '<td class="px-5 py-2.5 font-mono text-xs text-gray-400">' + recId + '</td>' +
            '<td class="px-5 py-2.5 text-xs text-gray-500 max-w-xs truncate">' + detail + '</td>' +
            '</tr>';
    }).join('');
}

// ===== Helpers =====
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

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function detailRow(label, value) {
    return '<span class="detail-label">' + label + '</span><span class="detail-value">' + value + '</span>';
}

// ===== Event Detail Modal =====

function openEventDetail(idx) {
    const e = currentEventsData[idx];
    if (!e) return;

    const modal = document.getElementById('eventModal');
    const content = document.getElementById('modalContent');
    const title = document.getElementById('modalTitle');

    const badgeClass = e.status === 'success' ? 'badge-success' : e.status === 'failed' ? 'badge-failed' : 'badge-error';
    const color = TYPE_COLORS[e.event_type] || '#6b7280';
    title.innerHTML = 'Event Detail &mdash; <span class="badge ' + badgeClass + '">' + e.status + '</span>';

    let html = '<div class="detail-grid">';
    html += detailRow('Event ID', e.id);
    html += detailRow('Event Type', '<span class="inline-block w-2.5 h-2.5 rounded-full mr-1.5" style="background:' + color + '"></span>' + e.event_type);
    html += detailRow('Status', '<span class="badge ' + badgeClass + '">' + e.status + '</span>');
    html += detailRow('Timestamp', new Date(e.created_at).toLocaleString());
    html += detailRow('Duration', e.duration_ms ? e.duration_ms + ' ms' : '--');
    html += detailRow('API Key Hash', '<code class="text-xs bg-gray-800 px-1.5 py-0.5 rounded font-mono">' + (e.api_key_hash || '--') + '</code>');
    html += detailRow('Record ID', e.record_id ? '<code class="text-xs bg-gray-800 px-1.5 py-0.5 rounded font-mono">' + e.record_id + '</code>' : '<span class="text-gray-500">--</span>');
    html += detailRow('External ID', e.external_id || '<span class="text-gray-500">--</span>');
    html += '</div>';

    // Error detail section
    if (e.error_detail) {
        html += '<div class="mt-5">';
        html += '<p class="detail-label mb-2">Error Detail</p>';
        html += '<div class="error-box">' + escapeHtml(e.error_detail) + '</div>';
        html += '</div>';
    }

    // Metadata section
    if (e.metadata && Object.keys(e.metadata).length > 0) {
        html += '<div class="mt-5">';
        html += '<p class="detail-label mb-2">Metadata</p>';
        html += '<div class="metadata-box">' + escapeHtml(JSON.stringify(e.metadata, null, 2)) + '</div>';
        html += '</div>';
    }

    // Face image section (use ?thumb=1 for fast loading)
    if (e.record_id) {
        html += '<div class="mt-5">';
        html += '<p class="detail-label mb-2">Face Image</p>';
        html += '<div id="modalImageContainer" class="flex items-center justify-center bg-gray-800/50 rounded-lg p-4 min-h-[100px]">';
        html += '<div class="spinner"></div><span class="ml-3 text-xs text-gray-500">Loading image...</span>';
        html += '</div>';
        html += '</div>';
    }

    content.innerHTML = html;
    modal.classList.remove('hidden');
    document.body.style.overflow = 'hidden';

    // Load image asynchronously (thumbnail for speed)
    if (e.record_id) {
        loadEventImage(e.record_id);
    }
}

async function loadEventImage(recordId) {
    const container = document.getElementById('modalImageContainer');
    if (!container) return;
    try {
        const apiKey = document.getElementById('apiKey').value.trim();
        const headers = {};
        if (apiKey) headers['X-API-Key'] = apiKey;
        const resp = await fetch(window.location.origin + '/api/v1/records/' + recordId + '/image?thumb=1', { headers });
        if (!resp.ok) {
            container.innerHTML = '<span class="text-xs text-gray-500">Image not available (record may have been deleted)</span>';
            return;
        }
        const blob = await resp.blob();
        const url = URL.createObjectURL(blob);
        container.innerHTML = '<img src="' + url + '" class="face-image" alt="Face image" onload="URL.revokeObjectURL(this.src)">';
    } catch (err) {
        container.innerHTML = '<span class="text-xs text-red-400">Failed to load image</span>';
    }
}

function closeModal() {
    document.getElementById('eventModal').classList.add('hidden');
    document.getElementById('modalContent').innerHTML = '';
    document.body.style.overflow = '';
}

document.addEventListener('keydown', e => {
    if (e.key === 'Escape') closeModal();
});
</script>

</body>
</html>"""
