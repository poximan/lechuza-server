from __future__ import annotations

import sys

from waitress import serve

from src.startup_errors import PanelexemysStartupError


def main() -> int:
    try:
        from src.app import server
    except PanelexemysStartupError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    serve(server, listen="0.0.0.0:8052")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
