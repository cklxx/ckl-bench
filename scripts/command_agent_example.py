#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    payload = json.loads(sys.stdin.read())
    workspace = payload.get("workspace_path")
    if not workspace:
        print(json.dumps({"text": "NO_WORKSPACE"}))
        return 0

    config = Path(workspace) / "service.cfg"
    if config.exists():
        text = config.read_text(encoding="utf-8")
        text = text.replace("shadow_mode=false", "shadow_mode=true")
        config.write_text(text, encoding="utf-8")
        print(json.dumps({"text": "DONE"}))
        return 0

    print(json.dumps({"text": "NOOP"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
