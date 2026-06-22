"""Shared bootstrap for the per-entity seed scripts."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from seeding.scales import DEFAULT_SCALE, SCALES  # noqa: E402


def scale_arg(description: str) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=description)
    ap.add_argument("--scale", choices=list(SCALES), default=DEFAULT_SCALE)
    return ap.parse_args()
