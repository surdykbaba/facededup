#!/usr/bin/env python3
"""Bulk enrollment client — runs InsightFace locally, sends embeddings to API.

This is ~500-1000x faster than sending images to the API because:
1. Face inference runs locally (no HTTP overhead per image)
2. Embeddings are sent in batches of 1000 (bulk DB insert)
3. API only does a PostgreSQL INSERT, no inference

IMPORTANT — Embedding Compatibility:
    The package versions MUST match the API backend to produce identical
    embeddings. Mismatched insightface versions can change face alignment,
    leading to incompatible embeddings and broken dedup/matching.

    Required versions (must match backend):
      - insightface  >= 0.7.3, < 0.8
      - onnxruntime  >= 1.19.0
      - numpy        >= 1.26.0, < 2.0.0
      - opencv-python-headless >= 4.10.0

Usage:
    pip install "insightface>=0.7.3,<0.8" "onnxruntime>=1.19.0" \
                "opencv-python-headless>=4.10.0" "numpy>=1.26.0,<2.0.0" \
                requests psycopg2-binary

    # Run with defaults:
    python bulk_enroll_client.py

    # Override via env vars:
    SOURCE_DB_URL=postgresql://user:pass@host/db \
    FACEDEDUP_API_URL=https://face.ninauth.com \
    FACEDEDUP_API_KEY=your-key \
    START_NIN=10050000000 \
    python bulk_enroll_client.py
"""

import base64
import concurrent.futures
import logging
import os
import signal
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import psycopg2
import psycopg2.extras
import requests
from insightface.app import FaceAnalysis

# ── Configuration (matches Go client defaults) ──
API_URL = os.getenv("FACEDEDUP_API_URL", "https://face.ninauth.com")
API_KEY = os.getenv("FACEDEDUP_API_KEY", "")
SOURCE_DB_URL = os.getenv(
    "SOURCE_DB_URL",
    "postgres://pgbouncer_user:heRtAnKYrOCacReAdEntErMh@10.254.201.26:5432/nimc_mws2?sslmode=disable",
)

# Tuning
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "1000"))       # Embeddings per API request
FETCH_SIZE = int(os.getenv("FETCH_SIZE", "500"))         # Rows per DB fetch
MAX_UPLOAD_WORKERS = int(os.getenv("UPLOAD_WORKERS", "4"))
DET_SIZE = (320, 320)  # Must match API's FACE_DET_SIZE
MIN_PHOTO_BYTES = int(os.getenv("MIN_PHOTO_BYTES", "1000"))
HTTP_RETRIES = int(os.getenv("HTTP_RETRIES", "3"))

# Progress / resume
START_NIN = os.getenv("START_NIN", "")
PROGRESS_FILE = os.getenv("PROGRESS_FILE", "progress.txt")
JOB_ID = os.getenv("JOB_ID", f"bulk-{int(time.time())}")

# Graceful shutdown flag
_shutdown = False

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)


# ── Signal handling (graceful shutdown like Go client) ──
def _handle_signal(signum, frame):
    global _shutdown
    log.info("Received signal %d — finishing current batch then stopping...", signum)
    _shutdown = True


signal.signal(signal.SIGINT, _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)


@dataclass
class EmbeddingRecord:
    nin: str
    embedding: list[float]
    metadata: dict


# ── Progress file (matches Go client's progress.txt) ──
def read_progress(path: str) -> str:
    """Read last processed NIN from progress file."""
    try:
        return Path(path).read_text().strip()
    except FileNotFoundError:
        return ""


def write_progress(path: str, nin: str):
    """Write last processed NIN to progress file."""
    if nin:
        Path(path).write_text(nin)


# ── Photo normalization (matches Go client's normalizePhoto) ──
def normalize_photo(photo_data) -> bytes | None:
    """Convert photo column value to raw image bytes.

    Handles the same formats as the Go client:
    - Raw image bytes (JPEG/PNG/WebP)
    - PostgreSQL bytea (\\x hex prefix)
    - Base64 encoded strings
    - Data URLs (data:image/...;base64,...)
    """
    if photo_data is None:
        return None

    # Handle memoryview from psycopg2
    if isinstance(photo_data, memoryview):
        photo_data = bytes(photo_data)

    if isinstance(photo_data, bytes):
        # Check if it's already a raw image
        if _looks_like_image(photo_data):
            return photo_data

        # Try as string (hex bytea or base64)
        try:
            s = photo_data.decode("utf-8", errors="ignore").strip()
        except Exception:
            return None

        # PostgreSQL hex bytea: \xFFD8FFE0...
        if s.startswith("\\x"):
            try:
                decoded = bytes.fromhex(s[2:])
                if _looks_like_image(decoded):
                    return decoded
            except ValueError:
                pass

        # Base64
        decoded = _try_base64(s)
        if decoded and _looks_like_image(decoded):
            return decoded

        return None

    if isinstance(photo_data, str):
        s = photo_data.strip()

        # Data URL: data:image/jpeg;base64,...
        if s.startswith("data:image/"):
            parts = s.split(",", 1)
            if len(parts) == 2:
                decoded = _try_base64(parts[1])
                if decoded and _looks_like_image(decoded):
                    return decoded
            return None

        # PostgreSQL hex bytea
        if s.startswith("\\x"):
            try:
                decoded = bytes.fromhex(s[2:])
                if _looks_like_image(decoded):
                    return decoded
            except ValueError:
                pass

        # Base64
        decoded = _try_base64(s)
        if decoded and _looks_like_image(decoded):
            return decoded

        return None

    return None


def _looks_like_image(b: bytes) -> bool:
    """Check for JPEG/PNG/WebP magic bytes."""
    if len(b) < 12:
        return False
    # JPEG
    if b[0] == 0xFF and b[1] == 0xD8 and b[2] == 0xFF:
        return True
    # PNG
    if b[:8] == b"\x89PNG\r\n\x1a\n":
        return True
    # WebP
    if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
        return True
    return False


def _try_base64(s: str) -> bytes | None:
    """Try standard and raw base64 decoding."""
    s = s.strip().strip('"')
    for decoder in (base64.b64decode, base64.urlsafe_b64decode):
        try:
            return decoder(s)
        except Exception:
            continue
    # Try with padding
    try:
        padded = s + "=" * (4 - len(s) % 4)
        return base64.b64decode(padded)
    except Exception:
        return None


# ── InsightFace model ──
def init_face_analyzer() -> FaceAnalysis:
    """Initialize InsightFace with buffalo_l model (matches API backend)."""
    os.environ["OMP_NUM_THREADS"] = "4"
    os.environ["OPENBLAS_NUM_THREADS"] = "4"

    log.info("Loading InsightFace buffalo_l model (det_size=%s)...", DET_SIZE)
    analyzer = FaceAnalysis(
        name="buffalo_l",
        providers=["CPUExecutionProvider"],
    )
    analyzer.prepare(ctx_id=-1, det_size=DET_SIZE)
    log.info("Model loaded successfully")
    return analyzer


def extract_embedding(analyzer: FaceAnalysis, image_bytes: bytes) -> np.ndarray | None:
    """Extract 512-dim face embedding. Matches API's face_service.py pipeline."""
    try:
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return None

        # Resize large images (matches face_service._decode_and_resize max_dim=640)
        h, w = img.shape[:2]
        if max(h, w) > 640:
            scale = 640 / max(h, w)
            img = cv2.resize(
                img, (int(w * scale), int(h * scale)),
                interpolation=cv2.INTER_AREA,
            )

        faces = analyzer.get(img)
        if len(faces) != 1:
            return None  # Skip: no face or multiple faces

        return faces[0].normed_embedding
    except Exception:
        return None


# ── DB fetch with keyset pagination (matches Go client's fetchBatchAfterNIN) ──
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
    """Fetch next batch of rows using keyset pagination."""
    with conn.cursor() as cur:
        cur.execute(FETCH_QUERY, (MIN_PHOTO_BYTES, last_nin, last_nin, FETCH_SIZE))
        return cur.fetchall()


# ── API upload with retry (matches Go client's retry logic) ──
def send_batch_with_retry(
    session: requests.Session, records: list[EmbeddingRecord]
) -> dict:
    """Send a batch of embeddings to the API with retry."""
    payload = {
        "records": [
            {
                "embedding": rec.embedding,
                "name": rec.nin,
                "external_id": rec.nin,
                "metadata": rec.metadata,
            }
            for rec in records
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
                headers={
                    "X-API-Key": API_KEY,
                    "Content-Type": "application/json",
                },
                timeout=120,
            )
            # Don't retry client errors (except 429)
            if 400 <= resp.status_code < 500 and resp.status_code != 429:
                resp.raise_for_status()

            if resp.status_code == 429:
                wait = attempt * 2
                log.warning("Rate limited (429), waiting %ds before retry %d/%d",
                            wait, attempt, HTTP_RETRIES)
                time.sleep(wait)
                continue

            resp.raise_for_status()
            return resp.json()

        except Exception as e:
            last_err = e
            if attempt < HTTP_RETRIES:
                wait = attempt * 2
                log.warning("Upload retry %d/%d: %s (waiting %ds)",
                            attempt, HTTP_RETRIES, e, wait)
                time.sleep(wait)

    raise last_err


# ── Main loop ──
def main():
    global _shutdown

    if not API_KEY:
        log.fatal("FACEDEDUP_API_KEY is required (set via env var)")
        sys.exit(1)

    analyzer = init_face_analyzer()

    # HTTP session with connection pooling
    http_session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(
        pool_connections=MAX_UPLOAD_WORKERS,
        pool_maxsize=MAX_UPLOAD_WORKERS,
    )
    http_session.mount("https://", adapter)
    http_session.mount("http://", adapter)

    # Determine start position (resume from progress file or env var)
    last_nin = START_NIN
    if not last_nin:
        last_nin = read_progress(PROGRESS_FILE)
        if last_nin:
            log.info("Resuming from progress file: %s", last_nin)

    # Connect to source database
    log.info("Connecting to source database...")
    conn = psycopg2.connect(SOURCE_DB_URL)
    conn.set_session(autocommit=True)  # Read-only, no transaction needed

    log.info("Starting bulk enrollment (job_id=%s, start_nin=%s)...", JOB_ID, last_nin or "(beginning)")

    total_fetched = 0
    total_embedded = 0
    total_enrolled = 0
    total_skipped = 0
    total_failed = 0
    batch_buffer: list[EmbeddingRecord] = []
    start_time = time.time()

    # Thread pool for concurrent API uploads
    upload_executor = concurrent.futures.ThreadPoolExecutor(max_workers=MAX_UPLOAD_WORKERS)
    pending_futures: list[concurrent.futures.Future] = []

    def drain_futures(block: bool = False):
        """Check completed upload futures and collect results."""
        nonlocal total_enrolled, total_failed
        if block:
            done_futures = list(concurrent.futures.as_completed(pending_futures))
        else:
            done_futures = [f for f in pending_futures if f.done()]
        for f in done_futures:
            pending_futures.remove(f)
            try:
                result = f.result()
                total_enrolled += result["total_success"]
                total_failed += result["total_failed"]
            except Exception as e:
                log.error("Batch upload failed: %s", e)
                total_failed += BATCH_SIZE

    def flush_batch():
        """Send current batch buffer to API."""
        nonlocal batch_buffer
        if not batch_buffer:
            return
        batch_to_send = batch_buffer[:]
        batch_buffer = []
        future = upload_executor.submit(send_batch_with_retry, http_session, batch_to_send)
        pending_futures.append(future)
        drain_futures(block=False)

    # Main fetch loop — keyset pagination like Go client
    while not _shutdown:
        rows = fetch_batch(conn, last_nin)
        if not rows:
            log.info("No more rows to fetch. Done.")
            break

        total_fetched += len(rows)

        for nin, photo in rows:
            if _shutdown:
                break

            last_nin = nin

            # Normalize photo (handle bytea hex, base64, raw bytes)
            image_bytes = normalize_photo(photo)
            if image_bytes is None or len(image_bytes) < MIN_PHOTO_BYTES:
                total_skipped += 1
                continue

            # Extract embedding locally
            embedding = extract_embedding(analyzer, image_bytes)
            if embedding is None:
                total_skipped += 1
                continue

            total_embedded += 1
            batch_buffer.append(EmbeddingRecord(
                nin=str(nin),
                embedding=embedding.tolist(),
                metadata={"nin": str(nin), "source": "public.nimc_mws3"},
            ))

            # Flush when batch is full
            if len(batch_buffer) >= BATCH_SIZE:
                flush_batch()

                # Save progress
                write_progress(PROGRESS_FILE, last_nin)

                # Log stats
                elapsed = time.time() - start_time
                rate = total_embedded / elapsed if elapsed > 0 else 0
                eta_hours = (50_000_000 - total_embedded) / rate / 3600 if rate > 0 else 0
                log.info(
                    "Fetched: %d | Embedded: %d | Enrolled: %d | Skipped: %d | "
                    "Failed: %d | Rate: %.1f rec/sec | Elapsed: %.1f min | "
                    "ETA: %.1f hrs | Last NIN: %s",
                    total_fetched, total_embedded, total_enrolled, total_skipped,
                    total_failed, rate, elapsed / 60, eta_hours, last_nin,
                )

    # Flush remaining buffer
    flush_batch()

    # Save final progress
    write_progress(PROGRESS_FILE, last_nin)

    # Wait for all pending uploads
    if pending_futures:
        log.info("Waiting for %d pending uploads to complete...", len(pending_futures))
        drain_futures(block=True)

    upload_executor.shutdown(wait=True)
    conn.close()

    elapsed = time.time() - start_time
    rate = total_embedded / elapsed if elapsed > 0 else 0
    log.info("=" * 60)
    log.info("BULK ENROLLMENT %s", "STOPPED (signal)" if _shutdown else "COMPLETE")
    log.info("Job ID:      %s", JOB_ID)
    log.info("Fetched:     %d", total_fetched)
    log.info("Embedded:    %d", total_embedded)
    log.info("Enrolled:    %d", total_enrolled)
    log.info("Skipped:     %d (no face / multi-face / bad photo)", total_skipped)
    log.info("Failed:      %d", total_failed)
    log.info("Last NIN:    %s", last_nin)
    log.info("Total time:  %.1f minutes (%.1f hours)", elapsed / 60, elapsed / 3600)
    log.info("Avg rate:    %.1f records/sec", rate)
    log.info("=" * 60)
    if not _shutdown:
        log.info("NEXT STEPS:")
        log.info("1. Rebuild HNSW index: POST %s/api/v1/admin/index/create", API_URL)
        log.info("2. Re-enable security checks in deploy workflow")
    else:
        log.info("Resume with: START_NIN=%s python %s", last_nin, __file__)


if __name__ == "__main__":
    main()
