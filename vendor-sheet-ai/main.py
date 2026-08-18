from __future__ import annotations

import argparse
import json
from pathlib import Path

from services.pipeline import process_file
from storage.state import StateStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Vendor sheet processing CLI")
    parser.add_argument("file_path", nargs="?", help="Path to the source CSV file")
    parser.add_argument("--status", action="store_true", help="Show whether the file was processed")
    args = parser.parse_args()

    if args.status:
        store = StateStore()
        print(json.dumps({"processed_files": store.list_processed_files()}))
        return

    if not args.file_path:
        parser.error("Please provide a file path")

    result = process_file(Path(args.file_path))
    print(json.dumps({
        "file_name": result.file_name,
        "status": result.status,
        "rows": result.normalized_rows,
        "issues": [issue.__dict__ for issue in result.issues],
    }, indent=2))


if __name__ == "__main__":
    main()
