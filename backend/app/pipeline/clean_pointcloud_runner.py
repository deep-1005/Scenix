"""
Standalone subprocess entry point for point cloud cleaning.

Run as: python -m app.pipeline.clean_pointcloud_runner --input X --output Y --job-dir Z

This exists so clean_point_cloud() runs in its OWN process, isolated from
the Celery worker. If Open3D segfaults or the OS OOM-killer terminates this
process, only THIS subprocess dies — the Celery worker (and the rest of
the pipeline orchestration in tasks.py) survives and can report a clear
error instead of silently hanging forever.

On success, prints the stats dict as a single line of JSON as the LAST
line of stdout — tasks.py parses that line to get the cleaning results
back into the main process.
"""
import argparse
import json
import sys
import logging

logging.basicConfig(level=logging.INFO, format="[clean-subprocess] %(message)s")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--job-dir", required=True)
    args = parser.parse_args()

    # Import here (not at module top) so argparse errors surface fast
    # without waiting on Open3D's import time.
    from app.pipeline.clean_pointcloud import clean_point_cloud

    try:
        stats = clean_point_cloud(
            input_ply=args.input,
            output_ply=args.output,
            job_output_dir=args.job_dir,
        )
    except Exception as e:
        logging.error(f"Cleaning failed: {e}")
        sys.exit(1)

    # IMPORTANT: this must be the last line printed, and must be valid JSON
    # on its own line — tasks.py reads it back via subprocess.run().
    print(json.dumps(stats))
    sys.exit(0)


if __name__ == "__main__":
    main()