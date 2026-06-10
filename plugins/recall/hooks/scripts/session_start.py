#!/usr/bin/env python3
"""Keep RECALL quiet until explicitly invoked from a user prompt."""

from __future__ import annotations

import json


def main() -> None:
    print(json.dumps({"continue": True}))


if __name__ == "__main__":
    main()
