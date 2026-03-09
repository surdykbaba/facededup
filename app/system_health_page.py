def get_system_health_html() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>FaceDedup &mdash; System Health</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
    <style>
        body { font-family: 'Inter', system-ui, -apple-system, sans-serif; }
        .card { background: #1f2937; border-radius: 12px; border: 1px solid #374151; }
        .gauge-ring { transition: stroke-dashoffset 0.6s ease; }
        .status-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
        .dot-green { background: #10b981; }
        .dot-yellow { background: #f59e0b; }
        .dot-red { background: #ef4444; }
        .dot-gray { background: #6b7280; }
        .spinner { border: 3px solid #374151; border-top: 3px solid #3b82f6; border-radius: 50%; width: 20px; height: 20px; animation: spin 0.8s linear infinite; display: inline-block; }
        @keyframes spin { to { transform: rotate(360deg); } }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
        .animate-pulse-slow { animation: pulse 2s ease-in-out infinite; }
        ::-webkit-scrollbar { width: 6px; height: 6px; }
        ::-webkit-scrollbar-track { background: #1f2937; }
        ::-webkit-scrollbar-thumb { background: #4b5563; border-radius: 3px; }
        .core-bar { height: 18px; border-radius: 4px; transition: width 0.5s ease; min-width: 2px; }
        .info-row { display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid #374151; }
        .info-row:last-child { border-bottom: none; }
        .info-label { color: #9ca3af; font-size: 13px; }
        .info-value { color: #e5e7eb; font-size: 13px; font-weight: 500; font-variant-numeric: tabular-nums; }
        /* Light theme overrides */
        html.light { color-scheme: light; }
        html.light body { background: #f8fafc !important; color: #1e293b !important; }
        html.light .card { background: #fff !important; border-color: #e2e8f0 !important; box-shadow: 0 1px 3px rgba(0,0,0,0.06); }
        html.light header { background: #fff !important; }
        html.light .bg-gray-950 { background: #fff !important; }
        html.light .border-gray-800, html.light .border-gray-700 { border-color: #e2e8f0 !important; }
        html.light .bg-gray-800 { background: #f1f5f9 !important; }
        html.light .bg-gray-900 { background: #f8fafc !important; }
        html.light .text-white { color: #0f172a !important; }
        html.light .text-gray-100 { color: #1e293b !important; }
        html.light .text-gray-200 { color: #334155 !important; }
        html.light .text-gray-300 { color: #475569 !important; }
        html.light .text-gray-400 { color: #64748b !important; }
        html.light .text-gray-500 { color: #94a3b8 !important; }
        html.light .divide-gray-800 > * + * { border-color: #e2e8f0 !important; }
        html.light .bg-gray-700 { background: #e2e8f0 !important; }
        html.light input, html.light select { background: #f1f5f9 !important; border-color: #cbd5e1 !important; color: #334155 !important; }
        html.light input::placeholder { color: #94a3b8 !important; }
        html.light footer { border-color: #e2e8f0 !important; }
        html.light .info-row { border-color: #e2e8f0 !important; }
        html.light .info-label { color: #64748b !important; }
        html.light .info-value { color: #334155 !important; }
        html.light ::-webkit-scrollbar-track { background: #f1f5f9; }
        html.light ::-webkit-scrollbar-thumb { background: #cbd5e1; }
    </style>
</head>
<body class="bg-gray-900 text-gray-100 min-h-screen">

    <!-- Header -->
    <header class="bg-gray-950 border-b border-gray-800">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 py-4">
            <div class="flex flex-wrap items-center justify-between gap-4">
                <div class="flex items-center gap-3">
                    <div class="w-8 h-8 bg-emerald-600 rounded-lg flex items-center justify-center">
                        <svg class="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z"/>
                        </svg>
                    </div>
                    <div>
                        <h1 class="text-xl font-bold text-white">System Health</h1>
                        <p class="text-xs text-gray-500">CPU, Memory, Disk &amp; Process monitoring</p>
                    </div>
                </div>
                <div class="flex flex-wrap items-center gap-3">
                    <a href="/dashboard" class="text-sm text-gray-400 hover:text-white transition">&#8592; Dashboard</a>
                    <div class="h-4 w-px bg-gray-700"></div>
                    <button onclick="toggleTheme()" id="themeToggle" class="p-1.5 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-white transition" title="Toggle light/dark theme">
                        <svg id="themeIconSun" class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z"/></svg>
                        <svg id="themeIconMoon" class="w-4 h-4 hidden" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z"/></svg>
                    </button>
                    <div class="h-4 w-px bg-gray-700"></div>
                    <div class="relative">
                        <input type="password" id="apiKey" placeholder="X-API-Key"
                            class="bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm font-mono text-gray-300 w-48 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none pr-12">
                        <button onclick="toggleKeyVis()" id="keyToggleBtn" class="absolute right-2 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300 text-xs">show</button>
                    </div>
                    <button onclick="saveKey()" class="bg-blue-600 hover:bg-blue-700 text-white px-3 py-1.5 rounded-lg text-sm font-medium transition">Save</button>
                </div>
            </div>
            <div class="flex flex-wrap items-center gap-3 mt-3">
                <!-- Server Tabs -->
                <div id="serverTabs" class="flex bg-gray-800 rounded-lg p-0.5">
                    <button onclick="selectServer(0)" data-server="0" class="server-tab px-3 py-1 rounded-md text-xs font-medium transition bg-blue-600 text-white">This Server</button>
                </div>
                <button onclick="refreshData()" class="flex items-center gap-1.5 bg-gray-800 hover:bg-gray-700 border border-gray-700 px-3 py-1.5 rounded-lg text-xs font-medium transition">
                    <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>
                    Refresh
                </button>
                <div class="flex items-center gap-2 ml-auto text-xs text-gray-500">
                    <span class="status-dot dot-green animate-pulse-slow"></span>
                    <span>Auto-refresh 5s</span>
                    <span class="text-gray-600">|</span>
                    <span id="lastRefresh">Loading...</span>
                </div>
            </div>
        </div>
    </header>

    <main class="max-w-7xl mx-auto px-4 sm:px-6 py-6 space-y-6">

        <!-- Error Banner -->
        <div id="errorBanner" class="hidden bg-red-900/50 border border-red-800 rounded-lg p-4 text-sm text-red-300">
            <strong>API Key Required:</strong> Enter your API key above to load system data.
        </div>

        <!-- KPI Gauges Row -->
        <div class="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <!-- CPU Gauge -->
            <div class="card p-5 flex flex-col items-center">
                <p class="text-xs text-gray-400 uppercase tracking-wider font-medium mb-3">CPU Usage</p>
                <div class="relative" style="width:120px; height:120px;">
                    <svg viewBox="0 0 36 36" class="w-full h-full -rotate-90">
                        <circle cx="18" cy="18" r="15.9" fill="none" stroke="#374151" stroke-width="2.5"/>
                        <circle id="cpuRing" cx="18" cy="18" r="15.9" fill="none" stroke="#3b82f6" stroke-width="2.5" stroke-linecap="round" class="gauge-ring"
                            stroke-dasharray="100" stroke-dashoffset="100"/>
                    </svg>
                    <div class="absolute inset-0 flex flex-col items-center justify-center">
                        <span class="text-2xl font-bold text-white tabular-nums" id="cpuPercent">--</span>
                        <span class="text-[10px] text-gray-500">percent</span>
                    </div>
                </div>
                <p class="text-xs text-gray-500 mt-2" id="cpuCores">-- cores</p>
            </div>
            <!-- Memory Gauge -->
            <div class="card p-5 flex flex-col items-center">
                <p class="text-xs text-gray-400 uppercase tracking-wider font-medium mb-3">Memory</p>
                <div class="relative" style="width:120px; height:120px;">
                    <svg viewBox="0 0 36 36" class="w-full h-full -rotate-90">
                        <circle cx="18" cy="18" r="15.9" fill="none" stroke="#374151" stroke-width="2.5"/>
                        <circle id="memRing" cx="18" cy="18" r="15.9" fill="none" stroke="#8b5cf6" stroke-width="2.5" stroke-linecap="round" class="gauge-ring"
                            stroke-dasharray="100" stroke-dashoffset="100"/>
                    </svg>
                    <div class="absolute inset-0 flex flex-col items-center justify-center">
                        <span class="text-2xl font-bold text-white tabular-nums" id="memPercent">--</span>
                        <span class="text-[10px] text-gray-500">percent</span>
                    </div>
                </div>
                <p class="text-xs text-gray-500 mt-2" id="memSummary">-- / -- GB</p>
            </div>
            <!-- Disk Gauge -->
            <div class="card p-5 flex flex-col items-center">
                <p class="text-xs text-gray-400 uppercase tracking-wider font-medium mb-3">Disk</p>
                <div class="relative" style="width:120px; height:120px;">
                    <svg viewBox="0 0 36 36" class="w-full h-full -rotate-90">
                        <circle cx="18" cy="18" r="15.9" fill="none" stroke="#374151" stroke-width="2.5"/>
                        <circle id="diskRing" cx="18" cy="18" r="15.9" fill="none" stroke="#f59e0b" stroke-width="2.5" stroke-linecap="round" class="gauge-ring"
                            stroke-dasharray="100" stroke-dashoffset="100"/>
                    </svg>
                    <div class="absolute inset-0 flex flex-col items-center justify-center">
                        <span class="text-2xl font-bold text-white tabular-nums" id="diskPercent">--</span>
                        <span class="text-[10px] text-gray-500">percent</span>
                    </div>
                </div>
                <p class="text-xs text-gray-500 mt-2" id="diskSummary">-- / -- GB</p>
            </div>
            <!-- Load Average -->
            <div class="card p-5 flex flex-col items-center">
                <p class="text-xs text-gray-400 uppercase tracking-wider font-medium mb-3">Load Average</p>
                <div class="relative" style="width:120px; height:120px;">
                    <svg viewBox="0 0 36 36" class="w-full h-full -rotate-90">
                        <circle cx="18" cy="18" r="15.9" fill="none" stroke="#374151" stroke-width="2.5"/>
                        <circle id="loadRing" cx="18" cy="18" r="15.9" fill="none" stroke="#10b981" stroke-width="2.5" stroke-linecap="round" class="gauge-ring"
                            stroke-dasharray="100" stroke-dashoffset="100"/>
                    </svg>
                    <div class="absolute inset-0 flex flex-col items-center justify-center">
                        <span class="text-2xl font-bold text-white tabular-nums" id="loadValue">--</span>
                        <span class="text-[10px] text-gray-500">1 min avg</span>
                    </div>
                </div>
                <p class="text-xs text-gray-500 mt-2" id="loadSummary">5m: -- | 15m: --</p>
            </div>
        </div>

        <!-- CPU Per-Core Usage -->
        <div class="card p-5">
            <h3 class="text-sm font-medium text-gray-300 mb-4">CPU Per-Core Usage</h3>
            <div id="coreGrid" class="grid grid-cols-4 sm:grid-cols-8 lg:grid-cols-10 gap-1.5">
                <div class="text-center text-xs text-gray-600 py-4 col-span-full">Loading...</div>
            </div>
        </div>

        <!-- Detail Cards Row -->
        <div class="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <!-- Memory Details -->
            <div class="card p-5">
                <h3 class="text-sm font-medium text-gray-300 mb-4 flex items-center gap-2">
                    <svg class="w-4 h-4 text-violet-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"/></svg>
                    Memory Details
                </h3>
                <div id="memDetails" class="space-y-0">
                    <div class="info-row"><span class="info-label">Total RAM</span><span class="info-value" id="memTotal">--</span></div>
                    <div class="info-row"><span class="info-label">Used</span><span class="info-value" id="memUsed">--</span></div>
                    <div class="info-row"><span class="info-label">Available</span><span class="info-value" id="memAvail">--</span></div>
                    <div class="info-row"><span class="info-label">Swap Total</span><span class="info-value" id="swapTotal">--</span></div>
                    <div class="info-row"><span class="info-label">Swap Used</span><span class="info-value" id="swapUsed">--</span></div>
                </div>
            </div>
            <!-- Disk Details -->
            <div class="card p-5">
                <h3 class="text-sm font-medium text-gray-300 mb-4 flex items-center gap-2">
                    <svg class="w-4 h-4 text-amber-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4"/></svg>
                    Disk Details
                </h3>
                <div id="diskDetails" class="space-y-0">
                    <div class="info-row"><span class="info-label">Total</span><span class="info-value" id="diskTotal">--</span></div>
                    <div class="info-row"><span class="info-label">Used</span><span class="info-value" id="diskUsed">--</span></div>
                    <div class="info-row"><span class="info-label">Free</span><span class="info-value" id="diskFree">--</span></div>
                    <div class="info-row"><span class="info-label">I/O Read</span><span class="info-value" id="ioRead">--</span></div>
                    <div class="info-row"><span class="info-label">I/O Write</span><span class="info-value" id="ioWrite">--</span></div>
                </div>
            </div>
            <!-- Network & Processes -->
            <div class="card p-5">
                <h3 class="text-sm font-medium text-gray-300 mb-4 flex items-center gap-2">
                    <svg class="w-4 h-4 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8.111 16.404a5.5 5.5 0 017.778 0M12 20h.01m-7.08-7.071c3.904-3.905 10.236-3.905 14.141 0M1.394 9.393c5.857-5.858 15.355-5.858 21.213 0"/></svg>
                    Network &amp; Processes
                </h3>
                <div class="space-y-0">
                    <div class="info-row"><span class="info-label">Net Sent</span><span class="info-value" id="netSent">--</span></div>
                    <div class="info-row"><span class="info-label">Net Received</span><span class="info-value" id="netRecv">--</span></div>
                    <div class="info-row"><span class="info-label">Net Errors</span><span class="info-value" id="netErrors">--</span></div>
                    <div class="info-row"><span class="info-label">Gunicorn Workers</span><span class="info-value" id="gWorkers">--</span></div>
                    <div class="info-row"><span class="info-label">Total Processes</span><span class="info-value" id="totalProcs">--</span></div>
                </div>
            </div>
        </div>

        <!-- System Info -->
        <div class="card p-5">
            <h3 class="text-sm font-medium text-gray-300 mb-4 flex items-center gap-2">
                <svg class="w-4 h-4 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z"/></svg>
                System Information
            </h3>
            <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-8">
                <div class="info-row"><span class="info-label">Hostname</span><span class="info-value" id="sysHostname">--</span></div>
                <div class="info-row"><span class="info-label">OS</span><span class="info-value" id="sysOS">--</span></div>
                <div class="info-row"><span class="info-label">Architecture</span><span class="info-value" id="sysArch">--</span></div>
                <div class="info-row"><span class="info-label">Python</span><span class="info-value" id="sysPython">--</span></div>
                <div class="info-row"><span class="info-label">Uptime</span><span class="info-value" id="sysUptime">--</span></div>
                <div class="info-row"><span class="info-label">Boot Time</span><span class="info-value" id="sysBoot">--</span></div>
            </div>
        </div>

    </main>

    <!-- Footer -->
    <footer class="border-t border-gray-800 mt-8">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 py-4 flex flex-wrap items-center justify-between text-xs text-gray-500">
            <span>FaceDedup &mdash; System Health Monitor</span>
            <span>Data refreshes automatically every 5 seconds</span>
        </div>
    </footer>

<script>
// ===== State =====
let refreshInterval = null;
const REFRESH_MS = 5000;
let clusterData = null;  // cached cluster health response
let selectedServer = 0;  // index into clusterData.servers

// ===== Init =====
document.addEventListener('DOMContentLoaded', () => {
    const saved = sessionStorage.getItem('facededup_dashboard_key');
    if (saved) document.getElementById('apiKey').value = saved;
    refreshData();
    startAutoRefresh();
});

// ===== API Key =====
function saveKey() {
    const key = document.getElementById('apiKey').value.trim();
    if (key) {
        sessionStorage.setItem('facededup_dashboard_key', key);
        refreshData();
    }
}

function toggleKeyVis() {
    const inp = document.getElementById('apiKey');
    const btn = document.getElementById('keyToggleBtn');
    if (inp.type === 'password') { inp.type = 'text'; btn.textContent = 'hide'; }
    else { inp.type = 'password'; btn.textContent = 'show'; }
}

document.getElementById('apiKey').addEventListener('keydown', e => { if (e.key === 'Enter') saveKey(); });

// ===== Auto Refresh =====
function startAutoRefresh() {
    if (refreshInterval) clearInterval(refreshInterval);
    refreshInterval = setInterval(refreshData, REFRESH_MS);
}

document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
        if (refreshInterval) { clearInterval(refreshInterval); refreshInterval = null; }
    } else {
        refreshData();
        startAutoRefresh();
    }
});

// ===== API Helper =====
async function sysApi(path) {
    const baseUrl = window.location.origin + '/api/v1';
    const apiKey = document.getElementById('apiKey').value.trim();
    const headers = {};
    if (apiKey) headers['X-API-Key'] = apiKey;
    const resp = await fetch(baseUrl + path, { headers });
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    return resp.json();
}

// ===== Server Selection =====
function selectServer(idx) {
    selectedServer = idx;
    document.querySelectorAll('.server-tab').forEach((b, i) => {
        if (i === idx) { b.classList.add('bg-blue-600', 'text-white'); b.classList.remove('text-gray-400'); }
        else { b.classList.remove('bg-blue-600', 'text-white'); b.classList.add('text-gray-400'); }
    });
    if (clusterData && clusterData.servers && clusterData.servers[idx]) {
        const srv = clusterData.servers[idx];
        if (srv.system_health) {
            renderAll(srv.system_health);
        } else if (idx === 0) {
            // Local server: fetch directly
            sysApi('/admin/system-health').then(renderAll).catch(e => console.error(e));
        }
    }
}

function buildServerTabs(servers) {
    const container = document.getElementById('serverTabs');
    container.innerHTML = servers.map((s, i) => {
        const label = s.server_name || ('Server ' + (i + 1));
        const role = s.server_role === 'primary' ? 'P' : 'W';
        const isOk = s.status === 'healthy';
        const dotClass = isOk ? 'dot-green' : s.status === 'degraded' ? 'dot-yellow' : 'dot-red';
        const active = i === selectedServer;
        const cls = active ? 'bg-blue-600 text-white' : 'text-gray-400 hover:text-white';
        return '<button onclick="selectServer(' + i + ')" data-server="' + i + '" class="server-tab flex items-center gap-1.5 px-3 py-1 rounded-md text-xs font-medium transition ' + cls + '">' +
            '<span class="status-dot ' + dotClass + '" style="width:6px;height:6px;"></span>' +
            '<span>' + label + '</span>' +
            '<span class="text-[9px] opacity-60">' + role + '</span>' +
            '</button>';
    }).join('');
}

// ===== Main Refresh =====
async function refreshData() {
    const apiKey = document.getElementById('apiKey').value.trim();
    const banner = document.getElementById('errorBanner');
    if (!apiKey) { banner.classList.remove('hidden'); return; }
    banner.classList.add('hidden');

    try {
        // Fetch cluster health to discover servers
        const cluster = await sysApi('/admin/cluster-health');
        clusterData = cluster;

        // Enrich each server with its full system-health data
        // The primary (index 0) is local - fetch its full data directly
        if (cluster.servers && cluster.servers.length > 0) {
            const localData = await sysApi('/admin/system-health');
            cluster.servers[0].system_health = localData;

            // Build tabs if more than 1 server
            if (cluster.servers.length > 1) {
                buildServerTabs(cluster.servers);
            } else {
                buildServerTabs(cluster.servers);
            }

            // Render selected server
            if (selectedServer < cluster.servers.length) {
                const srv = cluster.servers[selectedServer];
                if (srv.system_health) {
                    renderAll(srv.system_health);
                } else if (selectedServer === 0) {
                    renderAll(localData);
                }
            }
        }
    } catch (err) {
        console.error('[SystemHealth] fetch failed:', err.message);
        // Fallback: try direct system-health
        try {
            const data = await sysApi('/admin/system-health');
            renderAll(data);
        } catch (e2) {
            console.error('[SystemHealth] fallback failed:', e2.message);
        }
    }

    document.getElementById('lastRefresh').textContent = 'Last refresh: ' + new Date().toLocaleTimeString();
}

// ===== Render =====
function setGauge(ringId, pct) {
    const offset = 100 - Math.min(pct, 100);
    document.getElementById(ringId).setAttribute('stroke-dashoffset', offset);
    // Color by severity
    const el = document.getElementById(ringId);
    if (pct >= 90) el.setAttribute('stroke', '#ef4444');
    else if (pct >= 75) el.setAttribute('stroke', '#f59e0b');
}

function renderAll(d) {
    // CPU
    const cpuPct = d.cpu.total_percent;
    setGauge('cpuRing', cpuPct);
    document.getElementById('cpuPercent').textContent = cpuPct.toFixed(1) + '%';
    document.getElementById('cpuCores').textContent = d.cpu.logical_cores + ' cores (' + d.cpu.physical_cores + ' physical)';

    // Memory
    setGauge('memRing', d.memory.percent);
    document.getElementById('memPercent').textContent = d.memory.percent.toFixed(1) + '%';
    document.getElementById('memSummary').textContent = d.memory.used_gb + ' / ' + d.memory.total_gb + ' GB';

    // Disk
    setGauge('diskRing', d.disk.percent);
    document.getElementById('diskPercent').textContent = d.disk.percent.toFixed(1) + '%';
    document.getElementById('diskSummary').textContent = d.disk.used_gb + ' / ' + d.disk.total_gb + ' GB';

    // Load
    const loadPct = Math.min((d.load_average.load_1m / d.cpu.logical_cores) * 100, 100);
    setGauge('loadRing', loadPct);
    document.getElementById('loadValue').textContent = d.load_average.load_1m.toFixed(1);
    document.getElementById('loadSummary').textContent = '5m: ' + d.load_average.load_5m.toFixed(1) + ' | 15m: ' + d.load_average.load_15m.toFixed(1);

    // Per-core bars
    renderCoreGrid(d.cpu.per_core_percent);

    // Memory details
    document.getElementById('memTotal').textContent = d.memory.total_gb + ' GB';
    document.getElementById('memUsed').textContent = d.memory.used_gb + ' GB';
    document.getElementById('memAvail').textContent = d.memory.available_gb + ' GB';
    document.getElementById('swapTotal').textContent = d.memory.swap_total_gb + ' GB';
    document.getElementById('swapUsed').textContent = d.memory.swap_used_gb + ' GB (' + d.memory.swap_percent + '%)';

    // Disk details
    document.getElementById('diskTotal').textContent = d.disk.total_gb + ' GB';
    document.getElementById('diskUsed').textContent = d.disk.used_gb + ' GB';
    document.getElementById('diskFree').textContent = d.disk.free_gb + ' GB';
    document.getElementById('ioRead').textContent = (d.disk.io_read_gb || '--') + ' GB';
    document.getElementById('ioWrite').textContent = (d.disk.io_write_gb || '--') + ' GB';

    // Network
    document.getElementById('netSent').textContent = d.network.bytes_sent_gb + ' GB';
    document.getElementById('netRecv').textContent = d.network.bytes_recv_gb + ' GB';
    document.getElementById('netErrors').textContent = (d.network.errors_in + d.network.errors_out).toLocaleString();
    document.getElementById('gWorkers').textContent = d.processes.gunicorn_workers;
    document.getElementById('totalProcs').textContent = d.processes.total;

    // System info
    document.getElementById('sysHostname').textContent = d.system.hostname;
    document.getElementById('sysOS').textContent = d.system.os;
    document.getElementById('sysArch').textContent = d.system.architecture;
    document.getElementById('sysPython').textContent = d.system.python_version;
    document.getElementById('sysUptime').textContent = d.system.uptime;
    document.getElementById('sysBoot').textContent = new Date(d.system.boot_time).toLocaleString();
}

function renderCoreGrid(perCore) {
    const grid = document.getElementById('coreGrid');
    if (!perCore || !perCore.length) {
        grid.innerHTML = '<div class="text-center text-xs text-gray-600 py-4 col-span-full">No data</div>';
        return;
    }
    grid.innerHTML = perCore.map((pct, i) => {
        const color = pct >= 90 ? '#ef4444' : pct >= 70 ? '#f59e0b' : '#3b82f6';
        return '<div class="flex flex-col items-center gap-0.5" title="Core ' + i + ': ' + pct.toFixed(1) + '%">' +
            '<div class="w-full bg-gray-700 rounded overflow-hidden" style="height:18px;">' +
            '<div class="core-bar" style="width:' + Math.max(pct, 2) + '%; background:' + color + '; height:100%;"></div>' +
            '</div>' +
            '<span class="text-[9px] text-gray-500 tabular-nums">' + Math.round(pct) + '%</span>' +
            '</div>';
    }).join('');
}

// ===== Theme Toggle =====
function toggleTheme() {
    const isLight = document.documentElement.classList.toggle('light');
    localStorage.setItem('facededup_theme', isLight ? 'light' : 'dark');
    updateThemeIcons();
}

function updateThemeIcons() {
    const isLight = document.documentElement.classList.contains('light');
    document.getElementById('themeIconSun').classList.toggle('hidden', isLight);
    document.getElementById('themeIconMoon').classList.toggle('hidden', !isLight);
}

// Apply saved theme
(function() {
    const saved = localStorage.getItem('facededup_theme');
    if (saved === 'light') document.documentElement.classList.add('light');
    updateThemeIcons();
})();
</script>

</body>
</html>"""
