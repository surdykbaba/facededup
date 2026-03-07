import os

bind = "0.0.0.0:8000"
workers = int(os.getenv("WORKERS", 4))
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
