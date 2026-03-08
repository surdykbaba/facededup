#!/usr/bin/env python3
"""Bulk enrollment client — parallel InsightFace inference + batch API upload.

Uses multiprocessing to run N InsightFace workers in parallel, each on its
own CPU core. Results are batched and sent to /enroll/batch-embeddings.

IMPORTANT — Embedding Compatibility:
    pip install "insightface>=0.7.3,<0.8" "onnxruntime>=1.19.0" \
                "opencv-python-headless>=4.10.0" "numpy>=1.26.0,<2.0.0" \
                requests psycopg2-binary

Usage:
    FACEDEDUP_API_KEY=your-key python bulk_enroll_client.py

    # Override settings:
    INFERENCE_WORKERS=8 BATCH_SIZE=1000 START_NIN=10050000000 \
    FACEDEDUP_API_KEY=your-key python bulk_enroll_client.py
"""

import base64
import concurrent.futures
import logging
import multiprocessing as mp
import os
import signal
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import psycopg2
import requests

# ── Configuration ──
API_URL = os.getenv("FACEDEDUP_API_URL", "https://face.ninauth.com")
API_KEY = os.getenv("FACEDEDUP_API_KEY", "")
SOURCE_DB_URL = os.getenv(
    "SOURCE_DB_URL",
    "postgres://pgbouncer_user:heRtAnKYrOCacReAdEntErMh@10.254.201.26:5432/nimc_mws2?sslmode=disable",
)

# Tuning
INFERENCE_WORKERS = int(os.getenv("INFERENCE_WORKERS", str(max(1, mp.cpu_count() - 2))))
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "1000"))
FETCH_SIZE = int(os.getenv("FETCH_SIZE", "500"))
MAX_UPLOAD_WORKERS = int(os.getenv("UPLOAD_WORKERS", "4"))
DET_SIZE = (320, 320)
MIN_PHOTO_BYTES = int(os.getenv("MIN_PHOTO_BYTES", "1000"))
HTTP_RETRIES = int(os.getenv("HTTP_RETRIES", "3"))

# Progress / resume
START_NIN = os.getenv("START_NIN", "")
PROGRESS_FILE = os.getenv("PROGRESS_FILE", "progress.txt")
JOB_ID = os.getenv("JOB_ID", f"bulk-{int(time.time())}")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(processName)s] %(message)s",
)
log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
#  Worker process: each loads its own InsightFace model
# ═══════════════════════════════════════════════════════════

# Global per-process analyzer (loaded once per worker via initializer)
_worker_analyzer = None


def _worker_init():
    """Called once per worker process — loads InsightFace model."""
    global _worker_analyzer
    os.environ["OMP_NUM_THREADS"] = "2"   # 2 threads per worker to avoid contention
    os.environ["OPENBLAS_NUM_THREADS"] = "2"
    os.environ["MKL_NUM_THREADS"] = "2"

    import cv2  # noqa: F401 — ensure imported in worker
    import numpy as np  # noqa: F401
    from insightface.app import FaceAnalysis

    _worker_analyzer = FaceAnalysis(
        name="buffalo_l",
        providers=["CPUExecutionProvider"],
    )
    _worker_analyzer.prepare(ctx_id=-1, det_size=DET_SIZE)
    log.info("Worker model loaded (det_size=%s)", DET_SIZE)


def _worker_process_row(args: tuple) -> tuple | None:
    """Process a single (nin, photo_bytes) → (nin, embedding_list, metadata) or None.

    Runs in a worker process with its own InsightFace model.
    """
    import cv2
    import numpy as np

    nin, photo_data = args

    # Normalize photo
    image_bytes = _normalize_photo(photo_data)
    if image_bytes is None or len(image_bytes) < MIN_PHOTO_BYTES:
        return None

    # Extract embedding
    try:
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return None

        h, w = img.shape[:2]
        if max(h, w) > 640:
            scale = 640 / max(h, w)
            img = cv2.resize(img, (int(w * scale), int(h * scale)),
                             interpolation=cv2.INTER_AREA)

        faces = _worker_analyzer.get(img)
        if len(faces) != 1:
            return None

        embedding = faces[0].normed_embedding.tolist()
        return (str(nin), embedding, {"nin": str(nin), "source": "public.nimc_mws3"})
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════
#  Photo normalization (same as before, matches Go client)
# ═══════════════════════════════════════════════════════════

def _normalize_photo(photo_data) -> bytes | None:
    if photo_data is None:
        return None
    if isinstance(photo_data, memoryview):
        photo_data = bytes(photo_data)

    if isinstance(photo_data, bytes):
        if _looks_like_image(photo_data):
            return photo_data
        try:
            s = photo_data.decode("utf-8", errors="ignore").strip()
        except Exception:
            return None
        if s.startswith("\\x"):
            try:
                decoded = bytes.fromhex(s[2:])
                if _looks_like_image(decoded):
                    return decoded
            except ValueError:
                pass
        decoded = _try_base64(s)
        if decoded and _looks_like_image(decoded):
            return decoded
        return None

    if isinstance(photo_data, str):
        s = photo_data.strip()
        if s.startswith("data:image/"):
            parts = s.split(",", 1)
            if len(parts) == 2:
                decoded = _try_base64(parts[1])
                if decoded and _looks_like_image(decoded):
                    return decoded
            return None
        if s.startswith("\\x"):
            try:
                decoded = bytes.fromhex(s[2:])
                if _looks_like_image(decoded):
                    return decoded
            except ValueError:
                pass
        decoded = _try_base64(s)
        if decoded and _looks_like_image(decoded):
            return decoded
        return None
    return None


def _looks_like_image(b: bytes) -> bool:
    if len(b) < 12:
        return False
    if b[0] == 0xFF and b[1] == 0xD8 and b[2] == 0xFF:
        return True
    if b[:8] == b"\x89PNG\r\n\x1a\n":
        return True
    if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
        return True
    return False


def _try_base64(s: str) -> bytes | None:
    s = s.strip().strip('"')
    for decoder in (base64.b64decode, base64.urlsafe_b64decode):
        try:
            return decoder(s)
        except Exception:
            continue
    try:
        padded = s + "=" * (4 - len(s) % 4)
        return base64.b64decode(padded)
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════
#  Progress file
# ═══════════════════════════════════════════════════════════

def read_progress(path: str) -> str:
    try:
        return Path(path).read_text().strip()
    except FileNotFoundError:
        return ""


def write_progress(path: str, nin: str):
    if nin:
        Path(path).write_text(nin)


# ═══════════════════════════════════════════════════════════
#  DB fetch — keyset pagination
# ═══════════════════════════════════════════════════════════

FETCH_QUERY = """
    SELECT nin, photo
    FROM public.nimc_mws3
    WHERE nin IS NOT NULL
      AND photo IS NOT NULL
      AND octet_length(photo) > %s
      AND (%s = '' OR nin > %s)
    ORDER BY nin
    LIMIT %s
"""


def fetch_batch(conn, last_nin: str) -> list[tuple]:
    with conn.cursor() as cur:
        cur.execute(FETCH_QUERY, (MIN_PHOTO_BYTES, last_nin, last_nin, FETCH_SIZE))
        return cur.fetchall()


# ═══════════════════════════════════════════════════════════
#  API upload with retry
# ═══════════════════════════════════════════════════════════

def send_batch_with_retry(session: requests.Session, records: list[tuple]) -> dict:
    """Send batch of (nin, embedding, metadata) tuples to API."""
    payload = {
        "records": [
            {
                "embedding": emb,
                "name": nin,
                "external_id": nin,
                "metadata": meta,
            }
            for nin, emb, meta in records
        ],
        "skip_dedup": True,
        "job_id": JOB_ID,
    }

    last_err = None
    for attempt in range(1, HTTP_RETRIES + 1):
        try:
            resp = session.post(
                f"{API_URL}/api/v1/enroll/batch-embeddings",
                json=payload,
                headers={"X-API-Key": API_KEY, "Content-Type": "application/json"},
                timeout=120,
            )
            if 400 <= resp.status_code < 500 and resp.status_code != 429:
                resp.raise_for_status()
            if resp.status_code == 429:
                wait = attempt * 2
                log.warning("Rate limited (429), waiting %ds...", wait)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            last_err = e
            if attempt < HTTP_RETRIES:
                time.sleep(attempt * 2)
    raise last_err


# ═══════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════

def main():
    if not API_KEY:
        print("ERROR: FACEDEDUP_API_KEY is required", file=sys.stderr)
        sys.exit(1)

    log.info("=" * 60)
    log.info("Bulk Enrollment — Parallel InsightFace + Batch Upload")
    log.info("Inference workers: %d (CPU cores: %d)", INFERENCE_WORKERS, mp.cpu_count())
    log.info("Batch size: %d | Fetch size: %d | Upload workers: %d",
             BATCH_SIZE, FETCH_SIZE, MAX_UPLOAD_WORKERS)
    log.info("=" * 60)

    # HTTP session
    http_session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(
        pool_connections=MAX_UPLOAD_WORKERS,
        pool_maxsize=MAX_UPLOAD_WORKERS,
    )
    http_session.mount("https://", adapter)
    http_session.mount("http://", adapter)

    # Resume position
    last_nin = START_NIN
    if not last_nin:
        last_nin = read_progress(PROGRESS_FILE)
        if last_nin:
            log.info("Resuming from progress file: %s", last_nin)

    # Source DB
    log.info("Connecting to source database...")
    conn = psycopg2.connect(SOURCE_DB_URL)
    conn.set_session(autocommit=True)

    # Create process pool (each worker loads its own InsightFace model)
    log.info("Starting %d inference workers (loading models...)...", INFERENCE_WORKERS)
    pool = mp.Pool(
        processes=INFERENCE_WORKERS,
        initializer=_worker_init,
    )
    log.info("All workers ready.")

    # Upload thread pool
    upload_executor = concurrent.futures.ThreadPoolExecutor(max_workers=MAX_UPLOAD_WORKERS)
    pending_uploads: list[concurrent.futures.Future] = []

    total_fetched = 0
    total_embedded = 0
    total_enrolled = 0
    total_skipped = 0
    total_upload_failed = 0
    batch_buffer: list[tuple] = []  # (nin, embedding, metadata)
    start_time = time.time()
    stopped = False

    def drain_uploads(block: bool = False):
        nonlocal total_enrolled, total_upload_failed
        if block:
            done = list(concurrent.futures.as_completed(pending_uploads))
        else:
            done = [f for f in pending_uploads if f.done()]
        for f in done:
            pending_uploads.remove(f)
            try:
                result = f.result()
                total_enrolled += result["total_success"]
                total_upload_failed += result["total_failed"]
            except Exception as e:
                log.error("Upload failed: %s", e)
                total_upload_failed += BATCH_SIZE

    def flush_batch():
        nonlocal batch_buffer
        if not batch_buffer:
            return
        to_send = batch_buffer[:]
        batch_buffer = []
        future = upload_executor.submit(send_batch_with_retry, http_session, to_send)
        pending_uploads.append(future)
        drain_uploads(block=False)

    log.info("Starting bulk enrollment (job_id=%s, start=%s)...",
             JOB_ID, last_nin or "(beginning)")

    try:
        while not stopped:
            rows = fetch_batch(conn, last_nin)
            if not rows:
                log.info("No more rows. Done.")
                break

            total_fetched += len(rows)
            # Update last_nin to the last row in this fetch
            last_nin = rows[-1][0]

            # ── Parallel inference across all workers ──
            results = pool.map(_worker_process_row, rows, chunksize=max(1, len(rows) // INFERENCE_WORKERS))

            for r in results:
                if r is None:
                    total_skipped += 1
                    continue
                total_embedded += 1
                batch_buffer.append(r)

                if len(batch_buffer) >= BATCH_SIZE:
                    flush_batch()
                    write_progress(PROGRESS_FILE, last_nin)

                    elapsed = time.time() - start_time
                    rate = total_embedded / elapsed if elapsed > 0 else 0
                    remaining = 50_000_000 - total_embedded
                    eta_hrs = remaining / rate / 3600 if rate > 0 else 0
                    log.info(
                        "Fetched: %d | Embedded: %d | Enrolled: %d | Skipped: %d | "
                        "Failed: %d | Rate: %.1f/sec | ETA: %.1f hrs | NIN: %s",
                        total_fetched, total_embedded, total_enrolled,
                        total_skipped, total_upload_failed, rate, eta_hrs, last_nin,
                    )

    except KeyboardInterrupt:
        log.info("KeyboardInterrupt — stopping gracefully...")
        stopped = True
    finally:
        # Flush remaining
        flush_batch()
        write_progress(PROGRESS_FILE, last_nin)

        # Wait for uploads
        if pending_uploads:
            log.info("Waiting for %d pending uploads...", len(pending_uploads))
            drain_uploads(block=True)

        # Cleanup
        pool.terminate()
        pool.join()
        upload_executor.shutdown(wait=True)
        conn.close()

        elapsed = time.time() - start_time
        rate = total_embedded / elapsed if elapsed > 0 else 0
        log.info("=" * 60)
        log.info("BULK ENROLLMENT %s", "STOPPED" if stopped else "COMPLETE")
        log.info("Job ID:      %s", JOB_ID)
        log.info("Workers:     %d inference + %d upload", INFERENCE_WORKERS, MAX_UPLOAD_WORKERS)
        log.info("Fetched:     %d", total_fetched)
        log.info("Embedded:    %d", total_embedded)
        log.info("Enrolled:    %d", total_enrolled)
        log.info("Skipped:     %d", total_skipped)
        log.info("Failed:      %d", total_upload_failed)
        log.info("Last NIN:    %s", last_nin)
        log.info("Time:        %.1f min (%.1f hrs)", elapsed / 60, elapsed / 3600)
        log.info("Rate:        %.1f records/sec", rate)
        log.info("=" * 60)
        if not stopped:
            log.info("NEXT STEPS:")
            log.info("1. Rebuild HNSW index: POST %s/api/v1/admin/index/create", API_URL)
            log.info("2. Re-enable security checks in deploy workflow")
        else:
            log.info("Resume: START_NIN=%s python %s", last_nin, sys.argv[0])


if __name__ == "__main__":
    mp.set_start_method("spawn")  # Required for ONNX Runtime compatibility
    main()
