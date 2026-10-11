#!/usr/bin/env python3
"""
CLI script to import verified regulatory records into DToxOut database.

Usage:
    python scripts/import_regulations.py --file data/regulations_batch.json --manifest data/manifest.json --dry-run
    python scripts/import_regulations.py --file data/regulations_batch.csv --manifest data/manifest.json
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

# Add backend directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import db
from app.services.regulation_import_service import RegulationImportService, ManifestValidationError


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import verified regulatory records into DToxOut."
    )
    parser.add_argument(
        "--file",
        required=True,
        help="Path to JSON or CSV regulatory input file.",
    )
    parser.add_argument(
        "--manifest",
        required=False,
        help="Path to JSON manifest metadata file (optional if embedded in input JSON).",
    )
    parser.add_argument(
        "--format",
        choices=["json", "csv"],
        default=None,
        help="Input format (defaults to auto-detect from file extension).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and preview import without saving to database.",
    )

    args = parser.parse_args()

    file_path = Path(args.file).resolve()
    if not file_path.exists():
        print(f"Error: Input file '{file_path}' does not exist.", file=sys.stderr)
        sys.exit(1)

    file_format = args.format
    if not file_format:
        file_format = "csv" if file_path.suffix.lower() == ".csv" else "json"

    manifest_data = None
    if args.manifest:
        manifest_path = Path(args.manifest).resolve()
        if not manifest_path.exists():
            print(f"Error: Manifest file '{manifest_path}' does not exist.", file=sys.stderr)
            sys.exit(1)
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest_data = json.load(f)

    with open(file_path, "r", encoding="utf-8") as f:
        file_content = f.read()

    await db.connect()
    try:
        service = RegulationImportService(db)
        result = await service.import_regulations(
            data_input=file_content,
            manifest=manifest_data,
            file_format=file_format,
            dry_run=args.dry_run,
        )

        print("\n=== Regulatory Import Summary ===")
        print(f"Dry Run:          {result['dry_run']}")
        print(f"Created:          {result['created_count']}")
        print(f"Updated:          {result['updated_count']}")
        print(f"Skipped:          {result['skipped_count']}")
        print(f"Unmatched INCI:   {result['unmatched_count']}")
        print(f"Error Count:      {result['error_count']}")
        
        if result["unmatched_names"]:
            print("\n--- Unmatched INCI Names (Logged for Manual Review) ---")
            for name in result["unmatched_names"]:
                print(f"  - {name}")

        if result["warnings"]:
            print("\n--- Warnings ---")
            for warn in result["warnings"]:
                print(f"  - {warn}")

        if result["rejected_records"]:
            print(f"\n--- Rejected Records ({len(result['rejected_records'])}) ---")
            for rej in result["rejected_records"][:10]:  # Limit print to first 10
                print(f"  - Row {rej.get('row')}: {rej.get('reason')}")

        print("\nManifest Metadata:")
        print(f"  Organization:   {result['manifest']['sourceOrganization']}")
        print(f"  Source URL:     {result['manifest']['sourceUrl']}")
        print(f"  Retrieved Date: {result['manifest']['retrievedDate']}")
        print(f"  Licensing:      {result['manifest']['licenseNote']}")

    except ManifestValidationError as me:
        print(f"\nManifest Validation Error: {me.detail}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"\nImport Error: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        await db.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
