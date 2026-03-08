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

    # Adjust the DB connection and API settings below, then run:
    python bulk_enroll_client.py

    # Or with custom settings:
    FACEDEDUP_API_URL=https://face.ninauth.com \
    FACEDEDUP_API_KEY=your-key \
    SOURCE_DB_URL=postgresql://user:pass@host/db \
    python bulk_enroll_client.py
"""

import concurrent.futures
import io
import logging
import os
import sys
import time
from dataclasses import dataclass

import cv2
import numpy as np
import psycopg2
import psycopg2.extras
import requests
from insightface.app import FaceAnalysis

# ── Configuration ──
API_URL = os.getenv("FACEDEDUP_API_URL", "https://face.ninauth.com")
API_KEY = os.getenv("FACEDEDUP_API_KEY", "408dcf9bf4c9b2bf8f5fbeba87dd55365381cd571e7777b2cb0528eb85feac15")
SOURCE_DB_URL = os.getenv("SOURCE_DB_URL", "postgresql://user:pass@localhost:5432/source_db")

# Tuning
BATCH_SIZE = 1000          # Records per API request
FETCH_SIZE = 5000          # Rows fetched from source DB at a time
MAX_UPLOAD_WORKERS = 4     # Concurrent API upload threads
DET_SIZE = (320, 320)      # Detection size (match the API setting)
JOB_ID = os.getenv("JOB_ID", f"bulk-{int(time.time())}")

# Source DB query — adjust to match your schema
SOURCE_QUERY = """
    SELECT nin, image_data
    FROM public.nimc_mws3_batch_enroll
    WHERE nin NOT IN (
        SELECT external_id FROM already_processed
    )
    ORDER BY nin
"""
# If your source doesn't have an 'already_processed' table, simplify:
# SOURCE_QUERY = "SELECT nin, image_data FROM public.nimc_mws3_batch_enroll ORDER BY nin"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)


@dataclass
class EmbeddingRecord:
    nin: str
    embedding: list[float]
    metadata: dict


def init_face_analyzer() -> FaceAnalysis:
    """Initialize InsightFace with buffalo_l model."""
    # Set thread limits before loading model
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
    """Extract 512-dim face embedding from image bytes. Returns None on failure."""
    try:
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return None

        # Resize large images
        h, w = img.shape[:2]
        if max(h, w) > 640:
            scale = 640 / max(h, w)
            img = cv2.resize(img, (int(w * scale), int(h * scale)),
                             interpolation=cv2.INTER_AREA)

        faces = analyzer.get(img)
        if len(faces) != 1:
            return None  # Skip: no face or multiple faces

        return faces[0].normed_embedding
    except Exception:
        return None


def send_batch(session: requests.Session, records: list[EmbeddingRecord]) -> dict:
    """Send a batch of embeddings to the API."""
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

    resp = session.post(
        f"{API_URL}/api/v1/enroll/batch-embeddings",
        json=payload,
        headers={
            "X-API-Key": API_KEY,
            "Content-Type": "application/json",
        },
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()


def main():
    analyzer = init_face_analyzer()

    # HTTP session with connection pooling
    http_session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(
        pool_connections=MAX_UPLOAD_WORKERS,
        pool_maxsize=MAX_UPLOAD_WORKERS,
    )
    http_session.mount("https://", adapter)
    http_session.mount("http://", adapter)

    # Connect to source database
    log.info("Connecting to source database...")
    conn = psycopg2.connect(SOURCE_DB_URL)
    cursor = conn.cursor(name="bulk_fetch", cursor_factory=psycopg2.extras.DictCursor)
    cursor.itersize = FETCH_SIZE

    log.info("Starting bulk enrollment (job_id=%s)...", JOB_ID)
    cursor.execute(SOURCE_QUERY)

    total_processed = 0
    total_enrolled = 0
    total_skipped = 0
    total_failed = 0
    batch_buffer: list[EmbeddingRecord] = []
    start_time = time.time()

    # Thread pool for concurrent API uploads
    upload_executor = concurrent.futures.ThreadPoolExecutor(max_workers=MAX_UPLOAD_WORKERS)
    pending_futures: list[concurrent.futures.Future] = []

    for row in cursor:
        nin = row["nin"]
        image_data = row["image_data"]

        if image_data is None:
            total_skipped += 1
            continue

        # Handle memoryview/bytes
        if isinstance(image_data, memoryview):
            image_data = bytes(image_data)

        embedding = extract_embedding(analyzer, image_data)
        if embedding is None:
            total_skipped += 1
            continue

        batch_buffer.append(EmbeddingRecord(
            nin=str(nin),
            embedding=embedding.tolist(),
            metadata={"nin": str(nin), "source": "public.nimc_mws3_batch_enroll"},
        ))

        if len(batch_buffer) >= BATCH_SIZE:
            # Submit batch upload asynchronously
            batch_to_send = batch_buffer[:]
            batch_buffer = []

            future = upload_executor.submit(send_batch, http_session, batch_to_send)
            pending_futures.append(future)

            # Check completed futures
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

            total_processed += BATCH_SIZE
            elapsed = time.time() - start_time
            rate = total_processed / elapsed if elapsed > 0 else 0
            log.info(
                "Processed: %d | Enrolled: %d | Skipped: %d | Failed: %d | "
                "Rate: %.1f rec/sec | Elapsed: %.1f min",
                total_processed, total_enrolled, total_skipped, total_failed,
                rate, elapsed / 60,
            )

    # Send remaining buffer
    if batch_buffer:
        future = upload_executor.submit(send_batch, http_session, batch_buffer)
        pending_futures.append(future)

    # Wait for all uploads to complete
    log.info("Waiting for %d pending uploads to complete...", len(pending_futures))
    for f in concurrent.futures.as_completed(pending_futures):
        try:
            result = f.result()
            total_enrolled += result["total_success"]
            total_failed += result["total_failed"]
        except Exception as e:
            log.error("Batch upload failed: %s", e)

    upload_executor.shutdown(wait=True)
    cursor.close()
    conn.close()

    elapsed = time.time() - start_time
    log.info("=" * 60)
    log.info("BULK ENROLLMENT COMPLETE")
    log.info("Job ID:     %s", JOB_ID)
    log.info("Enrolled:   %d", total_enrolled)
    log.info("Skipped:    %d", total_skipped)
    log.info("Failed:     %d", total_failed)
    log.info("Total time: %.1f minutes (%.1f hours)", elapsed / 60, elapsed / 3600)
    log.info("Avg rate:   %.1f records/sec", total_enrolled / elapsed if elapsed > 0 else 0)
    log.info("=" * 60)
    log.info("NEXT STEPS:")
    log.info("1. Rebuild HNSW index: POST %s/api/v1/admin/index/create", API_URL)
    log.info("2. Re-enable security checks in deploy workflow")


if __name__ == "__main__":
    main()
