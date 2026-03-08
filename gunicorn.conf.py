import os

# ── ONNX Runtime thread tuning (MUST be set before importing onnxruntime) ──
# Each worker gets a bounded number of threads to prevent CPU contention.
# With 3 workers × 4 threads = 12 threads, fits well on 8-16 core machines.
os.environ.setdefault("OMP_NUM_THREADS", "4")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "4")
os.environ.setdefault("MKL_NUM_THREADS", "4")

bind = "0.0.0.0:8000"
workers = int(os.getenv("WORKERS", 3))
worker_class = "uvicorn.workers.UvicornWorker"
timeout = 300  # Batch operations and face detection can be slow on CPU
keepalive = 5
accesslog = "-"
errorlog = "-"
loglevel = os.getenv("LOG_LEVEL", "info").lower()
graceful_timeout = 30
# Each worker loads its own InsightFace model copy.
# ONNX Runtime doesn't handle forked processes reliably.
preload_app = False
