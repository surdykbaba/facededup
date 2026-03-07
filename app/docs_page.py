def get_docs_html() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>FaceDedup API</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        .try-panel { max-height: 0; overflow: hidden; transition: max-height 0.3s ease-out; }
        .try-panel.open { max-height: 2000px; transition: max-height 0.5s ease-in; }
        .spinner { border: 3px solid #e5e7eb; border-top: 3px solid #3b82f6; border-radius: 50%; width: 20px; height: 20px; animation: spin 0.8s linear infinite; display: inline-block; }
        @keyframes spin { to { transform: rotate(360deg); } }
        .thumb-preview { max-width: 80px; max-height: 80px; border-radius: 6px; object-fit: cover; border: 2px solid #e5e7eb; }
        pre.response { max-height: 400px; overflow: auto; }
    </style>
</head>
<body class="bg-gray-50 text-gray-900 min-h-screen">

    <!-- Header -->
    <header class="bg-gray-900 text-white">
        <div class="max-w-5xl mx-auto px-6 py-8">
            <div class="flex items-center gap-3 mb-2">
                <h1 class="text-3xl font-bold tracking-tight">FaceDedup API</h1>
                <span class="bg-blue-600 text-xs font-semibold px-2.5 py-1 rounded-full">v1.0.0</span>
            </div>
            <p class="text-gray-400 text-lg">Face deduplication &amp; matching API &mdash; enroll, match, compare, and verify faces</p>
            <div class="mt-4 flex items-center gap-2 text-sm text-gray-400">
                <span class="font-mono bg-gray-800 px-3 py-1 rounded" id="baseUrlDisplay"></span>
                <span id="healthDot" class="w-2.5 h-2.5 rounded-full bg-gray-600 inline-block"></span>
                <span id="healthText" class="text-xs">checking...</span>
            </div>
        </div>
    </header>

    <!-- API Key Bar -->
    <div class="sticky top-0 z-50 bg-white border-b shadow-sm">
        <div class="max-w-5xl mx-auto px-6 py-3 flex flex-wrap items-center gap-3">
            <label class="text-sm font-medium text-gray-600 whitespace-nowrap">API Key</label>
            <div class="relative flex-1 min-w-[200px] max-w-md">
                <input type="password" id="apiKey" placeholder="Enter your X-API-Key"
                    class="w-full border rounded-lg px-3 py-2 text-sm font-mono pr-10 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none">
                <button onclick="toggleKeyVisibility()" class="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 text-xs">show</button>
            </div>
            <button onclick="saveApiKey()" class="bg-gray-900 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-gray-700 transition">Save</button>
            <button onclick="checkHealth()" class="border px-4 py-2 rounded-lg text-sm font-medium hover:bg-gray-50 transition">Test Connection</button>
        </div>
    </div>

    <!-- Main Content -->
    <main class="max-w-5xl mx-auto px-6 py-8 space-y-6">

        <!-- Health -->
        <section>
            <h2 class="text-lg font-semibold text-gray-500 uppercase tracking-wider mb-4">Health</h2>
            <div class="bg-white rounded-xl border shadow-sm overflow-hidden">
                <div class="p-5">
                    <div class="flex items-center gap-3 mb-2">
                        <span class="bg-green-100 text-green-800 text-xs font-bold px-2.5 py-1 rounded">GET</span>
                        <code class="text-sm font-semibold">/api/v1/health</code>
                    </div>
                    <p class="text-sm text-gray-600 mb-3">Check API status, database, Redis, and face model health. No authentication required.</p>
                    <button onclick="togglePanel('health')" class="text-sm font-medium text-blue-600 hover:text-blue-800">Try it &darr;</button>
                </div>
                <div id="panel-health" class="try-panel border-t bg-gray-50">
                    <div class="p-5">
                        <button onclick="sendHealth()" id="btn-health" class="bg-green-600 text-white px-5 py-2 rounded-lg text-sm font-medium hover:bg-green-700 transition">Send</button>
                        <div id="res-health" class="mt-4"></div>
                    </div>
                </div>
            </div>
        </section>

        <!-- Enrollment -->
        <section>
            <h2 class="text-lg font-semibold text-gray-500 uppercase tracking-wider mb-4">Enrollment</h2>
            <div class="bg-white rounded-xl border shadow-sm overflow-hidden">
                <div class="p-5">
                    <div class="flex items-center gap-3 mb-2">
                        <span class="bg-blue-100 text-blue-800 text-xs font-bold px-2.5 py-1 rounded">POST</span>
                        <code class="text-sm font-semibold">/api/v1/enroll</code>
                    </div>
                    <p class="text-sm text-gray-600 mb-1">Enroll a new face. Detects face, runs liveness checks, extracts embedding, stores record.</p>
                    <p class="text-xs text-gray-400 mb-3">Returns duplicate_info if a matching face already exists in the database.</p>
                    <button onclick="togglePanel('enroll')" class="text-sm font-medium text-blue-600 hover:text-blue-800">Try it &darr;</button>
                </div>
                <div id="panel-enroll" class="try-panel border-t bg-gray-50">
                    <div class="p-5 space-y-4">
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-1">Image <span class="text-red-500">*</span></label>
                            <input type="file" id="enroll-image" accept=".jpg,.jpeg,.png,.webp" onchange="previewFile(this, 'enroll-preview')" class="text-sm">
                            <div id="enroll-preview" class="mt-2"></div>
                        </div>
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-1">Additional Frames <span class="text-gray-400 font-normal">(optional, 2-4 for multi-frame liveness)</span></label>
                            <input type="file" id="enroll-frames" accept=".jpg,.jpeg,.png,.webp" multiple class="text-sm">
                        </div>
                        <div class="grid grid-cols-2 gap-4">
                            <div>
                                <label class="block text-sm font-medium text-gray-700 mb-1">Name</label>
                                <input type="text" id="enroll-name" placeholder="John Doe" class="w-full border rounded-lg px-3 py-2 text-sm">
                            </div>
                            <div>
                                <label class="block text-sm font-medium text-gray-700 mb-1">External ID</label>
                                <input type="text" id="enroll-external-id" placeholder="EMP-001" class="w-full border rounded-lg px-3 py-2 text-sm">
                            </div>
                        </div>
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-1">Metadata <span class="text-gray-400 font-normal">(JSON)</span></label>
                            <textarea id="enroll-metadata" rows="2" placeholder='{"department": "engineering"}' class="w-full border rounded-lg px-3 py-2 text-sm font-mono"></textarea>
                        </div>
                        <div class="flex items-center gap-2">
                            <input type="checkbox" id="enroll-skip-liveness" class="rounded">
                            <label for="enroll-skip-liveness" class="text-sm text-gray-700">Skip liveness check</label>
                        </div>
                        <button onclick="sendEnroll()" id="btn-enroll" class="bg-blue-600 text-white px-5 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 transition">Send</button>
                        <div id="res-enroll" class="mt-2"></div>
                    </div>
                </div>
            </div>
        </section>

        <!-- Matching -->
        <section>
            <h2 class="text-lg font-semibold text-gray-500 uppercase tracking-wider mb-4">Matching</h2>
            <div class="bg-white rounded-xl border shadow-sm overflow-hidden">
                <div class="p-5">
                    <div class="flex items-center gap-3 mb-2">
                        <span class="bg-blue-100 text-blue-800 text-xs font-bold px-2.5 py-1 rounded">POST</span>
                        <code class="text-sm font-semibold">/api/v1/match</code>
                    </div>
                    <p class="text-sm text-gray-600 mb-3">Search enrolled faces for matches. Upload a face image and find similar faces in the database (1:N search).</p>
                    <button onclick="togglePanel('match')" class="text-sm font-medium text-blue-600 hover:text-blue-800">Try it &darr;</button>
                </div>
                <div id="panel-match" class="try-panel border-t bg-gray-50">
                    <div class="p-5 space-y-4">
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-1">Image <span class="text-red-500">*</span></label>
                            <input type="file" id="match-image" accept=".jpg,.jpeg,.png,.webp" onchange="previewFile(this, 'match-preview')" class="text-sm">
                            <div id="match-preview" class="mt-2"></div>
                        </div>
                        <div class="grid grid-cols-2 gap-4">
                            <div>
                                <label class="block text-sm font-medium text-gray-700 mb-1">Threshold <span class="text-gray-400 font-normal">(0-1, default 0.4)</span></label>
                                <input type="number" id="match-threshold" min="0" max="1" step="0.01" placeholder="0.4" class="w-full border rounded-lg px-3 py-2 text-sm">
                            </div>
                            <div>
                                <label class="block text-sm font-medium text-gray-700 mb-1">Limit <span class="text-gray-400 font-normal">(1-100, default 10)</span></label>
                                <input type="number" id="match-limit" min="1" max="100" placeholder="10" class="w-full border rounded-lg px-3 py-2 text-sm">
                            </div>
                        </div>
                        <div class="flex items-center gap-2">
                            <input type="checkbox" id="match-skip-liveness" class="rounded">
                            <label for="match-skip-liveness" class="text-sm text-gray-700">Skip liveness check</label>
                        </div>
                        <button onclick="sendMatch()" id="btn-match" class="bg-blue-600 text-white px-5 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 transition">Send</button>
                        <div id="res-match" class="mt-2"></div>
                    </div>
                </div>
            </div>
        </section>

        <!-- Comparison -->
        <section>
            <h2 class="text-lg font-semibold text-gray-500 uppercase tracking-wider mb-4">Comparison</h2>
            <div class="bg-white rounded-xl border shadow-sm overflow-hidden">
                <div class="p-5">
                    <div class="flex items-center gap-3 mb-2">
                        <span class="bg-blue-100 text-blue-800 text-xs font-bold px-2.5 py-1 rounded">POST</span>
                        <code class="text-sm font-semibold">/api/v1/compare</code>
                    </div>
                    <p class="text-sm text-gray-600 mb-3">Compare two face images directly (1:1). No database lookup &mdash; returns similarity score between the two faces.</p>
                    <button onclick="togglePanel('compare')" class="text-sm font-medium text-blue-600 hover:text-blue-800">Try it &darr;</button>
                </div>
                <div id="panel-compare" class="try-panel border-t bg-gray-50">
                    <div class="p-5 space-y-4">
                        <div class="grid grid-cols-2 gap-4">
                            <div>
                                <label class="block text-sm font-medium text-gray-700 mb-1">Image A <span class="text-red-500">*</span></label>
                                <input type="file" id="compare-image-a" accept=".jpg,.jpeg,.png,.webp" onchange="previewFile(this, 'compare-preview-a')" class="text-sm">
                                <div id="compare-preview-a" class="mt-2"></div>
                            </div>
                            <div>
                                <label class="block text-sm font-medium text-gray-700 mb-1">Image B <span class="text-red-500">*</span></label>
                                <input type="file" id="compare-image-b" accept=".jpg,.jpeg,.png,.webp" onchange="previewFile(this, 'compare-preview-b')" class="text-sm">
                                <div id="compare-preview-b" class="mt-2"></div>
                            </div>
                        </div>
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-1">Threshold <span class="text-gray-400 font-normal">(0-1, default 0.4)</span></label>
                            <input type="number" id="compare-threshold" min="0" max="1" step="0.01" placeholder="0.4" class="w-full border rounded-lg px-3 py-2 text-sm max-w-xs">
                        </div>
                        <div class="flex items-center gap-2">
                            <input type="checkbox" id="compare-skip-liveness" class="rounded">
                            <label for="compare-skip-liveness" class="text-sm text-gray-700">Skip liveness check</label>
                        </div>
                        <button onclick="sendCompare()" id="btn-compare" class="bg-blue-600 text-white px-5 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 transition">Send</button>
                        <div id="res-compare" class="mt-2"></div>
                    </div>
                </div>
            </div>
        </section>

        <!-- Liveness -->
        <section>
            <h2 class="text-lg font-semibold text-gray-500 uppercase tracking-wider mb-4">Liveness Detection</h2>

            <!-- Single Frame -->
            <div class="bg-white rounded-xl border shadow-sm overflow-hidden mb-4">
                <div class="p-5">
                    <div class="flex items-center gap-3 mb-2">
                        <span class="bg-blue-100 text-blue-800 text-xs font-bold px-2.5 py-1 rounded">POST</span>
                        <code class="text-sm font-semibold">/api/v1/liveness</code>
                    </div>
                    <p class="text-sm text-gray-600 mb-3">Passive single-frame liveness check. Runs 15 heuristic + ML checks to detect spoofing (printed photos, screen replays, cartoons).</p>
                    <button onclick="togglePanel('liveness')" class="text-sm font-medium text-blue-600 hover:text-blue-800">Try it &darr;</button>
                </div>
                <div id="panel-liveness" class="try-panel border-t bg-gray-50">
                    <div class="p-5 space-y-4">
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-1">Image <span class="text-red-500">*</span></label>
                            <input type="file" id="liveness-image" accept=".jpg,.jpeg,.png,.webp" onchange="previewFile(this, 'liveness-preview')" class="text-sm">
                            <div id="liveness-preview" class="mt-2"></div>
                        </div>
                        <button onclick="sendLiveness()" id="btn-liveness" class="bg-blue-600 text-white px-5 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 transition">Send</button>
                        <div id="res-liveness" class="mt-2"></div>
                    </div>
                </div>
            </div>

            <!-- Multi Frame -->
            <div class="bg-white rounded-xl border shadow-sm overflow-hidden">
                <div class="p-5">
                    <div class="flex items-center gap-3 mb-2">
                        <span class="bg-blue-100 text-blue-800 text-xs font-bold px-2.5 py-1 rounded">POST</span>
                        <code class="text-sm font-semibold">/api/v1/liveness/multi-frame</code>
                    </div>
                    <p class="text-sm text-gray-600 mb-3">Active multi-frame liveness. Upload 3-5 sequential images &mdash; verifies genuine inter-frame motion to detect static spoofs.</p>
                    <button onclick="togglePanel('multi-liveness')" class="text-sm font-medium text-blue-600 hover:text-blue-800">Try it &darr;</button>
                </div>
                <div id="panel-multi-liveness" class="try-panel border-t bg-gray-50">
                    <div class="p-5 space-y-4">
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-1">Frames <span class="text-red-500">*</span> <span class="text-gray-400 font-normal">(select 3-5 sequential images)</span></label>
                            <input type="file" id="multi-liveness-frames" accept=".jpg,.jpeg,.png,.webp" multiple class="text-sm">
                        </div>
                        <button onclick="sendMultiLiveness()" id="btn-multi-liveness" class="bg-blue-600 text-white px-5 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 transition">Send</button>
                        <div id="res-multi-liveness" class="mt-2"></div>
                    </div>
                </div>
            </div>
        </section>

        <!-- Deduplication -->
        <section>
            <h2 class="text-lg font-semibold text-gray-500 uppercase tracking-wider mb-4">Deduplication</h2>
            <div class="bg-white rounded-xl border shadow-sm overflow-hidden">
                <div class="p-5">
                    <div class="flex items-center gap-3 mb-2">
                        <span class="bg-blue-100 text-blue-800 text-xs font-bold px-2.5 py-1 rounded">POST</span>
                        <code class="text-sm font-semibold">/api/v1/deduplicate</code>
                    </div>
                    <p class="text-sm text-gray-600 mb-3">Scan all enrolled records for duplicate face pairs. Returns pairs exceeding the similarity threshold.</p>
                    <button onclick="togglePanel('dedup')" class="text-sm font-medium text-blue-600 hover:text-blue-800">Try it &darr;</button>
                </div>
                <div id="panel-dedup" class="try-panel border-t bg-gray-50">
                    <div class="p-5 space-y-4">
                        <div class="grid grid-cols-2 gap-4">
                            <div>
                                <label class="block text-sm font-medium text-gray-700 mb-1">Threshold <span class="text-gray-400 font-normal">(0-1, default 0.4)</span></label>
                                <input type="number" id="dedup-threshold" min="0" max="1" step="0.01" placeholder="0.4" class="w-full border rounded-lg px-3 py-2 text-sm">
                            </div>
                            <div>
                                <label class="block text-sm font-medium text-gray-700 mb-1">Batch Size <span class="text-gray-400 font-normal">(10-1000, default 100)</span></label>
                                <input type="number" id="dedup-batch-size" min="10" max="1000" placeholder="100" class="w-full border rounded-lg px-3 py-2 text-sm">
                            </div>
                        </div>
                        <button onclick="sendDedup()" id="btn-dedup" class="bg-blue-600 text-white px-5 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 transition">Send</button>
                        <div id="res-dedup" class="mt-2"></div>
                    </div>
                </div>
            </div>
        </section>

        <!-- Records -->
        <section>
            <h2 class="text-lg font-semibold text-gray-500 uppercase tracking-wider mb-4">Records</h2>

            <!-- Get Record -->
            <div class="bg-white rounded-xl border shadow-sm overflow-hidden mb-4">
                <div class="p-5">
                    <div class="flex items-center gap-3 mb-2">
                        <span class="bg-green-100 text-green-800 text-xs font-bold px-2.5 py-1 rounded">GET</span>
                        <code class="text-sm font-semibold">/api/v1/records/{record_id}</code>
                    </div>
                    <p class="text-sm text-gray-600 mb-3">Retrieve an enrolled face record by its UUID.</p>
                    <button onclick="togglePanel('get-record')" class="text-sm font-medium text-blue-600 hover:text-blue-800">Try it &darr;</button>
                </div>
                <div id="panel-get-record" class="try-panel border-t bg-gray-50">
                    <div class="p-5 space-y-4">
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-1">Record ID <span class="text-red-500">*</span></label>
                            <input type="text" id="get-record-id" placeholder="550e8400-e29b-41d4-a716-446655440000" class="w-full border rounded-lg px-3 py-2 text-sm font-mono">
                        </div>
                        <button onclick="sendGetRecord()" id="btn-get-record" class="bg-green-600 text-white px-5 py-2 rounded-lg text-sm font-medium hover:bg-green-700 transition">Send</button>
                        <div id="res-get-record" class="mt-2"></div>
                    </div>
                </div>
            </div>

            <!-- Delete Record -->
            <div class="bg-white rounded-xl border shadow-sm overflow-hidden">
                <div class="p-5">
                    <div class="flex items-center gap-3 mb-2">
                        <span class="bg-red-100 text-red-800 text-xs font-bold px-2.5 py-1 rounded">DELETE</span>
                        <code class="text-sm font-semibold">/api/v1/records/{record_id}</code>
                    </div>
                    <p class="text-sm text-gray-600 mb-3">Delete an enrolled face record and its stored image.</p>
                    <button onclick="togglePanel('delete-record')" class="text-sm font-medium text-blue-600 hover:text-blue-800">Try it &darr;</button>
                </div>
                <div id="panel-delete-record" class="try-panel border-t bg-gray-50">
                    <div class="p-5 space-y-4">
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-1">Record ID <span class="text-red-500">*</span></label>
                            <input type="text" id="delete-record-id" placeholder="550e8400-e29b-41d4-a716-446655440000" class="w-full border rounded-lg px-3 py-2 text-sm font-mono">
                        </div>
                        <div class="flex items-center gap-2">
                            <input type="checkbox" id="delete-confirm" class="rounded" onchange="document.getElementById('btn-delete-record').disabled = !this.checked">
                            <label for="delete-confirm" class="text-sm text-red-600 font-medium">I confirm I want to delete this record</label>
                        </div>
                        <button onclick="sendDeleteRecord()" id="btn-delete-record" disabled class="bg-red-600 text-white px-5 py-2 rounded-lg text-sm font-medium hover:bg-red-700 transition disabled:opacity-40 disabled:cursor-not-allowed">Delete</button>
                        <div id="res-delete-record" class="mt-2"></div>
                    </div>
                </div>
            </div>
        </section>

    </main>

    <!-- Footer -->
    <footer class="bg-gray-100 border-t mt-12">
        <div class="max-w-5xl mx-auto px-6 py-6 text-sm text-gray-500 space-y-1">
            <p><strong>Authentication:</strong> All endpoints except <code>/health</code> require the <code>X-API-Key</code> header.</p>
            <p><strong>Rate Limit:</strong> 60 requests per 60-second window per API key.</p>
            <p><strong>Max Image Size:</strong> 10 MB (JPEG, PNG, WebP)</p>
        </div>
    </footer>

<script>
// ─── Config ───
const BASE_URL_KEY = 'facededup_base_url';
const API_KEY_KEY = 'facededup_api_key';

function getBaseUrl() {
    return document.getElementById('baseUrl')?.value || (window.location.origin + '/api/v1');
}

function getApiKey() {
    return document.getElementById('apiKey').value;
}

// Init
document.addEventListener('DOMContentLoaded', () => {
    const saved = sessionStorage.getItem(API_KEY_KEY);
    if (saved) document.getElementById('apiKey').value = saved;
    document.getElementById('baseUrlDisplay').textContent = window.location.origin + '/api/v1';
    checkHealth();
});

function saveApiKey() {
    sessionStorage.setItem(API_KEY_KEY, getApiKey());
    checkHealth();
}

function toggleKeyVisibility() {
    const inp = document.getElementById('apiKey');
    const btn = inp.nextElementSibling;
    if (inp.type === 'password') { inp.type = 'text'; btn.textContent = 'hide'; }
    else { inp.type = 'password'; btn.textContent = 'show'; }
}

// ─── Panel toggle ───
function togglePanel(id) {
    document.getElementById('panel-' + id).classList.toggle('open');
}

// ─── File preview ───
function previewFile(input, targetId) {
    const container = document.getElementById(targetId);
    container.innerHTML = '';
    if (input.files && input.files[0]) {
        const img = document.createElement('img');
        img.src = URL.createObjectURL(input.files[0]);
        img.className = 'thumb-preview';
        img.onload = () => URL.revokeObjectURL(img.src);
        container.appendChild(img);
    }
}

// ─── Response display ───
function showResponse(targetId, status, elapsed, data) {
    const el = document.getElementById(targetId);
    const color = status < 300 ? 'text-green-600' : status < 500 ? 'text-yellow-600' : 'text-red-600';
    const bgColor = status < 300 ? 'bg-green-50 border-green-200' : status < 500 ? 'bg-yellow-50 border-yellow-200' : 'bg-red-50 border-red-200';
    el.innerHTML = `
        <div class="flex items-center gap-3 mb-2">
            <span class="${color} font-bold text-sm">HTTP ${status}</span>
            <span class="text-gray-400 text-xs">${elapsed}ms</span>
        </div>
        <pre class="response ${bgColor} border rounded-lg p-4 text-xs font-mono whitespace-pre-wrap break-words">${escapeHtml(JSON.stringify(data, null, 2))}</pre>
    `;
}

function showError(targetId, err) {
    document.getElementById(targetId).innerHTML = `
        <div class="bg-red-50 border border-red-200 rounded-lg p-4 text-sm text-red-700">${escapeHtml(err.message || String(err))}</div>
    `;
}

function showLoading(targetId) {
    document.getElementById(targetId).innerHTML = '<div class="spinner"></div>';
}

function escapeHtml(str) {
    return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function setButtonLoading(btnId, loading) {
    const btn = document.getElementById(btnId);
    if (loading) { btn.disabled = true; btn.dataset.origText = btn.textContent; btn.innerHTML = '<span class="spinner"></span>'; }
    else { btn.disabled = false; btn.textContent = btn.dataset.origText || 'Send'; }
}

// ─── API calls ───
async function apiCall(method, path, { query, formData, pathParams } = {}) {
    const baseUrl = window.location.origin + '/api/v1';
    const apiKey = getApiKey();

    let url = baseUrl + path;
    if (pathParams) {
        for (const [k, v] of Object.entries(pathParams)) {
            url = url.replace('{' + k + '}', encodeURIComponent(v));
        }
    }

    if (query) {
        const params = new URLSearchParams();
        for (const [k, v] of Object.entries(query)) {
            if (v !== '' && v !== null && v !== undefined) params.append(k, v);
        }
        const qs = params.toString();
        if (qs) url += '?' + qs;
    }

    const headers = {};
    if (apiKey) headers['X-API-Key'] = apiKey;

    const options = { method, headers };
    if (formData) options.body = formData;

    const t0 = performance.now();
    const resp = await fetch(url, options);
    const elapsed = Math.round(performance.now() - t0);

    let data;
    const ct = resp.headers.get('content-type') || '';
    if (ct.includes('application/json')) { data = await resp.json(); }
    else { data = { raw: await resp.text() }; }

    return { status: resp.status, elapsed, data };
}

// ─── Health ───
async function checkHealth() {
    try {
        const { status, data } = await apiCall('GET', '/health');
        const dot = document.getElementById('healthDot');
        const txt = document.getElementById('healthText');
        if (status === 200 && data.status === 'healthy') {
            dot.className = 'w-2.5 h-2.5 rounded-full bg-green-500 inline-block';
            txt.textContent = 'connected';
            txt.className = 'text-xs text-green-400';
        } else {
            dot.className = 'w-2.5 h-2.5 rounded-full bg-yellow-500 inline-block';
            txt.textContent = 'degraded';
            txt.className = 'text-xs text-yellow-400';
        }
    } catch {
        document.getElementById('healthDot').className = 'w-2.5 h-2.5 rounded-full bg-red-500 inline-block';
        const txt = document.getElementById('healthText');
        txt.textContent = 'offline';
        txt.className = 'text-xs text-red-400';
    }
}

async function sendHealth() {
    setButtonLoading('btn-health', true);
    showLoading('res-health');
    try {
        const { status, elapsed, data } = await apiCall('GET', '/health');
        showResponse('res-health', status, elapsed, data);
    } catch (e) { showError('res-health', e); }
    setButtonLoading('btn-health', false);
}

// ─── Enroll ───
async function sendEnroll() {
    const fileInput = document.getElementById('enroll-image');
    if (!fileInput.files.length) { showError('res-enroll', { message: 'Please select an image' }); return; }

    setButtonLoading('btn-enroll', true);
    showLoading('res-enroll');
    try {
        const fd = new FormData();
        fd.append('image', fileInput.files[0]);

        const framesInput = document.getElementById('enroll-frames');
        for (const f of framesInput.files) fd.append('frames', f);

        const name = document.getElementById('enroll-name').value;
        const extId = document.getElementById('enroll-external-id').value;
        const meta = document.getElementById('enroll-metadata').value;
        const skipLive = document.getElementById('enroll-skip-liveness').checked;

        if (name) fd.append('name', name);
        if (extId) fd.append('external_id', extId);
        if (meta) fd.append('metadata', meta);
        if (skipLive) fd.append('skip_liveness', 'true');

        const { status, elapsed, data } = await apiCall('POST', '/enroll', { formData: fd });
        showResponse('res-enroll', status, elapsed, data);
    } catch (e) { showError('res-enroll', e); }
    setButtonLoading('btn-enroll', false);
}

// ─── Match ───
async function sendMatch() {
    const fileInput = document.getElementById('match-image');
    if (!fileInput.files.length) { showError('res-match', { message: 'Please select an image' }); return; }

    setButtonLoading('btn-match', true);
    showLoading('res-match');
    try {
        const fd = new FormData();
        fd.append('image', fileInput.files[0]);

        const query = {};
        const t = document.getElementById('match-threshold').value;
        const l = document.getElementById('match-limit').value;
        const s = document.getElementById('match-skip-liveness').checked;
        if (t) query.threshold = t;
        if (l) query.limit = l;
        if (s) query.skip_liveness = 'true';

        const { status, elapsed, data } = await apiCall('POST', '/match', { formData: fd, query });
        showResponse('res-match', status, elapsed, data);
    } catch (e) { showError('res-match', e); }
    setButtonLoading('btn-match', false);
}

// ─── Compare ───
async function sendCompare() {
    const fileA = document.getElementById('compare-image-a');
    const fileB = document.getElementById('compare-image-b');
    if (!fileA.files.length || !fileB.files.length) { showError('res-compare', { message: 'Please select both images' }); return; }

    setButtonLoading('btn-compare', true);
    showLoading('res-compare');
    try {
        const fd = new FormData();
        fd.append('image_a', fileA.files[0]);
        fd.append('image_b', fileB.files[0]);

        const query = {};
        const t = document.getElementById('compare-threshold').value;
        const s = document.getElementById('compare-skip-liveness').checked;
        if (t) query.threshold = t;
        if (s) query.skip_liveness = 'true';

        const { status, elapsed, data } = await apiCall('POST', '/compare', { formData: fd, query });
        showResponse('res-compare', status, elapsed, data);
    } catch (e) { showError('res-compare', e); }
    setButtonLoading('btn-compare', false);
}

// ─── Liveness ───
async function sendLiveness() {
    const fileInput = document.getElementById('liveness-image');
    if (!fileInput.files.length) { showError('res-liveness', { message: 'Please select an image' }); return; }

    setButtonLoading('btn-liveness', true);
    showLoading('res-liveness');
    try {
        const fd = new FormData();
        fd.append('image', fileInput.files[0]);
        const { status, elapsed, data } = await apiCall('POST', '/liveness', { formData: fd });
        showResponse('res-liveness', status, elapsed, data);
    } catch (e) { showError('res-liveness', e); }
    setButtonLoading('btn-liveness', false);
}

// ─── Multi-Frame Liveness ───
async function sendMultiLiveness() {
    const fileInput = document.getElementById('multi-liveness-frames');
    if (fileInput.files.length < 3) { showError('res-multi-liveness', { message: 'Please select at least 3 images' }); return; }

    setButtonLoading('btn-multi-liveness', true);
    showLoading('res-multi-liveness');
    try {
        const fd = new FormData();
        for (const f of fileInput.files) fd.append('frames', f);
        const { status, elapsed, data } = await apiCall('POST', '/liveness/multi-frame', { formData: fd });
        showResponse('res-multi-liveness', status, elapsed, data);
    } catch (e) { showError('res-multi-liveness', e); }
    setButtonLoading('btn-multi-liveness', false);
}

// ─── Deduplicate ───
async function sendDedup() {
    setButtonLoading('btn-dedup', true);
    showLoading('res-dedup');
    try {
        const query = {};
        const t = document.getElementById('dedup-threshold').value;
        const b = document.getElementById('dedup-batch-size').value;
        if (t) query.threshold = t;
        if (b) query.batch_size = b;

        const { status, elapsed, data } = await apiCall('POST', '/deduplicate', { query });
        showResponse('res-dedup', status, elapsed, data);
    } catch (e) { showError('res-dedup', e); }
    setButtonLoading('btn-dedup', false);
}

// ─── Get Record ───
async function sendGetRecord() {
    const id = document.getElementById('get-record-id').value.trim();
    if (!id) { showError('res-get-record', { message: 'Please enter a record ID' }); return; }

    setButtonLoading('btn-get-record', true);
    showLoading('res-get-record');
    try {
        const { status, elapsed, data } = await apiCall('GET', '/records/{record_id}', { pathParams: { record_id: id } });
        showResponse('res-get-record', status, elapsed, data);
    } catch (e) { showError('res-get-record', e); }
    setButtonLoading('btn-get-record', false);
}

// ─── Delete Record ───
async function sendDeleteRecord() {
    const id = document.getElementById('delete-record-id').value.trim();
    if (!id) { showError('res-delete-record', { message: 'Please enter a record ID' }); return; }

    setButtonLoading('btn-delete-record', true);
    showLoading('res-delete-record');
    try {
        const { status, elapsed, data } = await apiCall('DELETE', '/records/{record_id}', { pathParams: { record_id: id } });
        showResponse('res-delete-record', status, elapsed, data);
    } catch (e) { showError('res-delete-record', e); }
    setButtonLoading('btn-delete-record', false);
}
</script>

</body>
</html>"""
