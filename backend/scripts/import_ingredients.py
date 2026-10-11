"""
CLI Script for Batch Ingredient Import into DToxOut Knowledge Base.

Usage:
  python -m scripts.import_ingredients --file path/to/ingredients.json [--dry-run] [--manifest path/to/manifest.json]
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Dict

from prisma import Prisma
from app.services.import_service import ImportService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="DToxOut Verified Batch Ingredient Import Tool"
    )
    parser.add_argument(
        "--file",
        required=True,
        help="Path to JSON file containing ingredient import data.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate manifest and ingredient records without writing to the database.",
    )
    parser.add_argument(
        "--manifest",
        help="Optional path to separate JSON manifest file or inline JSON string.",
    )
    return parser.parse_args()


async def run_import(args: argparse.Namespace) -> int:
    file_path = Path(args.file)
    if not file_path.exists():
        print(f"Error: Input file '{file_path}' does not exist.", file=sys.stderr)
        return 1

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
    except Exception as e:
        print(f"Error reading JSON file '{file_path}': {e}", file=sys.stderr)
        return 1

    manifest = {}
    ingredients = []

    if isinstance(raw_data, dict):
        manifest = raw_data.get("manifest", {})
        ingredients = raw_data.get("ingredients", [])
    elif isinstance(raw_data, list):
        ingredients = raw_data

    # Override manifest if --manifest arg provided
    if args.manifest:
        manifest_path = Path(args.manifest)
        if manifest_path.exists():
            with open(manifest_path, "r", encoding="utf-8") as mf:
                manifest = json.load(mf)
        else:
            try:
                manifest = json.loads(args.manifest)
            except Exception:
                print(f"Error: Unable to parse --manifest argument.", file=sys.stderr)
                return 1

    payload = {
        "manifest": manifest,
        "ingredients": ingredients,
    }

    db = None
    if not args.dry_run:
        db = Prisma()
        await db.connect()

    try:
        service = ImportService(db=db)
        summary = await service.import_batch(payload, dry_run=args.dry_run)
    finally:
        if db and db.is_connected():
            await db.disconnect()

    print("\n" + "=" * 55)
    print(" === DToxOut Batch Ingredient Import Summary ===")
    print("=" * 55)
    print(f" Dry Run Mode  : {args.dry_run}")
    print(f" Total Records : {summary.get('total_records', 0)}")
    print(f" Created Count : {summary.get('created_count', 0)}")
    print(f" Updated Count : {summary.get('updated_count', 0)}")
    print(f" Skipped Count : {summary.get('skipped_count', 0)}")
    print(f" Error Count   : {summary.get('error_count', 0)}")
    
    if summary.get("warnings"):
        print("\n[Warnings]")
        for w in summary["warnings"]:
            print(f" - {w}")

    if summary.get("errors"):
        print("\n[Errors]")
        for err in summary["errors"]:
            print(f" ! {err}")
        print("=" * 55 + "\n")
        return 1

    print("=" * 55 + "\n")
    return 0


def main() -> None:
    args = parse_args()
    exit_code = asyncio.run(run_import(args))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
