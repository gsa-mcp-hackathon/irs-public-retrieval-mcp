"""Validate local cases or upload separated inputs/references to caller's Phoenix."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .data import load_examples, resolve_dataset


def main():
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path)
    parser.add_argument("--registry", type=Path, default=here / "datasets.yaml")
    parser.add_argument("--dataset-name", default="irs-public-retrieval")
    parser.add_argument("--phoenix-url")
    parser.add_argument("--upload", action="store_true")
    parser.add_argument("--work-dir", type=Path, required=True)
    args = parser.parse_args()
    path = args.dataset or resolve_dataset(args.registry, args.dataset_name)
    rows = load_examples(path)
    if not rows:
        raise ValueError("Dataset requires nonempty cases")
    receipt = {"dataset": str(path), "cases": len(rows), "uploaded": False}
    if args.upload:
        args.work_dir.mkdir(parents=True, exist_ok=True)
        os.environ["PHOENIX_WORKING_DIR"] = str(args.work_dir.resolve())
        import httpx

        from phoenix.client import Client

        if not args.phoenix_url:
            raise ValueError("Explicit --phoenix-url required for dataset upload")
        with httpx.Client(base_url=args.phoenix_url) as transport:
            client = Client(http_client=transport)
            dataset = client.datasets.create_dataset(
                name=args.dataset_name,
                inputs=[row["input"] for row in rows],
                outputs=[row["expected"] for row in rows],
                metadata=[{"case_id": row["id"], **row["metadata"]} for row in rows],
            )
            receipt.update(uploaded=True, dataset_id=dataset.id)
    print(json.dumps(receipt))


if __name__ == "__main__":
    main()
