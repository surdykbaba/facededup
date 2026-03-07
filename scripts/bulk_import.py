#!/usr/bin/env python3
"""
Bulk Import Helper for FaceDedup API

Workflow for importing 50M+ face records:

  1. Drop HNSW index (much faster inserts without incremental index updates):
     python scripts/bulk_import.py drop-index --api-url https://face.ninauth.com --api-key YOUR_KEY

  2. Run batch enrollment loop (e.g., 50,000 requests × 1,000 records each):
     python scripts/bulk_import.py upload --api-url https://face.ninauth.com --api-key YOUR_KEY --input embeddings.jsonl --batch-size 1000

  3. Rebuild HNSW index (one-pass build is orders of magnitude faster):
     python scripts/bulk_import.py create-index --api-url https://face.ninauth.com --api-key YOUR_KEY

  4. VACUUM ANALYZE for optimal query performance:
     python scripts/bulk_import.py vacuum --api-url https://face.ninauth.com --api-key YOUR_KEY

  5. Check progress:
     python scripts/bulk_import.py progress --api-url https://face.ninauth.com --api-key YOUR_KEY --job-id MY_JOB

Input format (JSONL - one JSON object per line):
  {"embedding": [0.1, 0.2, ...512 floats...], "name": "John Doe", "external_id": "EMP-001"}
  {"embedding": [0.3, 0.4, ...512 floats...], "name": "Jane Smith", "external_id": "EMP-002"}

The embedding field is required (512 floats). name, external_id, metadata, image_path are optional.
"""

import argparse
import json
import sys
import time
import uuid

import requests


def drop_index(args):
    """Drop the HNSW index before bulk import."""
    print("Dropping HNSW index...")
    resp = requests.post(
        f"{args.api_url}/api/v1/admin/index/drop",
        headers={"X-API-Key": args.api_key},
        timeout=60,
    )
    resp.raise_for_status()
    print(f"  Result: {resp.json()}")


def create_index(args):
    """Rebuild the HNSW index after bulk import."""
    print("Rebuilding HNSW index (CONCURRENTLY — this may take hours for 50M+ records)...")
    resp = requests.post(
        f"{args.api_url}/api/v1/admin/index/create",
        headers={"X-API-Key": args.api_key},
        timeout=600,
    )
    resp.raise_for_status()
    print(f"  Result: {resp.json()}")


def vacuum(args):
    """Run VACUUM ANALYZE after bulk import."""
    print("Running VACUUM ANALYZE...")
    resp = requests.post(
        f"{args.api_url}/api/v1/admin/vacuum",
        headers={"X-API-Key": args.api_key},
        timeout=600,
    )
    resp.raise_for_status()
    print(f"  Result: {resp.json()}")


def check_status(args):
    """Check HNSW index status and record count."""
    resp = requests.get(
        f"{args.api_url}/api/v1/admin/index/status",
        headers={"X-API-Key": args.api_key},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    print(f"  Total records: {data['total_records']:,}")
    print(f"  HNSW index exists: {data['index_exists']}")
    if data["hnsw_indexes"]:
        for idx in data["hnsw_indexes"]:
            print(f"    {idx['name']}: {idx['definition']}")


def upload(args):
    """Upload embeddings from a JSONL file in batches."""
    job_id = args.job_id or str(uuid.uuid4())[:8]
    print(f"Starting bulk upload (job_id: {job_id})")
    print(f"  Input: {args.input}")
    print(f"  Batch size: {args.batch_size}")
    print()

    total_success = 0
    total_failed = 0
    batch_num = 0
    batch = []

    start = time.time()

    with open(args.input, "r") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError as e:
                print(f"  ERROR: Invalid JSON at line {line_num}: {e}")
                total_failed += 1
                continue

            if "embedding" not in record or len(record["embedding"]) != 512:
                print(f"  ERROR: Invalid embedding at line {line_num} (need 512 floats)")
                total_failed += 1
                continue

            batch.append(record)

            if len(batch) >= args.batch_size:
                batch_num += 1
                success, failed = _send_batch(args, batch, job_id)
                total_success += success
                total_failed += failed
                elapsed = time.time() - start
                rate = total_success / elapsed if elapsed > 0 else 0
                print(
                    f"  Batch {batch_num}: +{success} success, +{failed} failed | "
                    f"Total: {total_success:,} ({rate:.0f} rec/sec)"
                )
                batch = []

    # Send remaining records
    if batch:
        batch_num += 1
        success, failed = _send_batch(args, batch, job_id)
        total_success += success
        total_failed += failed

    elapsed = time.time() - start
    print(f"\nDone! {total_success:,} enrolled, {total_failed:,} failed in {elapsed:.1f}s")
    print(f"  Average: {total_success / elapsed:.0f} records/sec")


def _send_batch(args, records, job_id):
    """Send a batch of records to the API."""
    payload = {
        "records": records,
        "skip_dedup": True,
        "job_id": job_id,
    }
    try:
        resp = requests.post(
            f"{args.api_url}/api/v1/enroll/batch-embeddings",
            json=payload,
            headers={"X-API-Key": args.api_key},
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["total_success"], data["total_failed"]
    except Exception as e:
        print(f"    BATCH ERROR: {e}")
        return 0, len(records)


def progress(args):
    """Check progress of a bulk upload job."""
    resp = requests.get(
        f"{args.api_url}/api/v1/enroll/batch-progress/{args.job_id}",
        headers={"X-API-Key": args.api_key},
        timeout=30,
    )
    if resp.status_code == 404:
        print(f"No progress found for job_id: {args.job_id}")
        return
    resp.raise_for_status()
    data = resp.json()
    print(f"  Job: {data['job_id']}")
    print(f"  Batches completed: {data['batches_completed']}")
    print(f"  Total success: {data['total_success']:,}")
    print(f"  Total failed: {data['total_failed']:,}")
    print(f"  Last updated: {data.get('last_updated', 'N/A')}")


def main():
    parser = argparse.ArgumentParser(
        description="FaceDedup Bulk Import Helper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--api-url", default="https://face.ninauth.com", help="API base URL")
    parser.add_argument("--api-key", required=True, help="API key for authentication")

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("drop-index", help="Drop HNSW index before bulk import")
    sub.add_parser("create-index", help="Rebuild HNSW index after bulk import")
    sub.add_parser("vacuum", help="Run VACUUM ANALYZE after bulk import")
    sub.add_parser("status", help="Check index status and record count")

    upload_parser = sub.add_parser("upload", help="Upload embeddings from JSONL file")
    upload_parser.add_argument("--input", required=True, help="Path to JSONL file")
    upload_parser.add_argument("--batch-size", type=int, default=1000, help="Records per batch")
    upload_parser.add_argument("--job-id", help="Job ID for progress tracking")

    progress_parser = sub.add_parser("progress", help="Check upload progress")
    progress_parser.add_argument("--job-id", required=True, help="Job ID to check")

    args = parser.parse_args()

    commands = {
        "drop-index": drop_index,
        "create-index": create_index,
        "vacuum": vacuum,
        "status": check_status,
        "upload": upload,
        "progress": progress,
    }

    try:
        commands[args.command](args)
    except requests.HTTPError as e:
        print(f"HTTP Error: {e.response.status_code} - {e.response.text}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(1)


if __name__ == "__main__":
    main()
