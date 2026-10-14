"""Validate only this repository's demo lab and write its own report."""

from pathlib import Path

from cloud_validation import CloudLab
from lab_validation import main

ROOT = Path(__file__).resolve().parents[1]

ADAPTER = CloudLab(ROOT, "azure-foundry-rag-agent", "rg-foundry-rag-demo", "rag")

if __name__ == "__main__":
    raise SystemExit(main(ADAPTER))
