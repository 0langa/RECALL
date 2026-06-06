#!/usr/bin/env python3
"""Validate and normalize RECALL categories."""

from __future__ import annotations

import argparse
import json

import config as recall_config


def main() -> None:
    parser = argparse.ArgumentParser(description="Reload and normalize RECALL memory categories.")
    parser.add_argument("--root")
    args = parser.parse_args()
    cfg = recall_config.load_config(args.root)
    recall_config.save_config(cfg, args.root)
    print(json.dumps({"categories": sorted(cfg["categories"])}, indent=2))


if __name__ == "__main__":
    main()
