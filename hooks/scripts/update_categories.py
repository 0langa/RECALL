#!/usr/bin/env python3
"""Hook wrapper for category reloads."""

from __future__ import annotations

import argparse
import json

import _recall_path  # noqa: F401
import config as recall_config


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root")
    args = parser.parse_args()
    cfg = recall_config.load_config(args.root)
    recall_config.save_config(cfg, args.root)
    print(json.dumps({"updated": True, "categories": sorted(cfg["categories"])}, indent=2))


if __name__ == "__main__":
    main()
