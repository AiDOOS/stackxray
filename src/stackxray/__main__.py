"""`python -m stackxray` - the V1 entry.

  python -m stackxray            -> open the browser form (default; what the launcher uses)
  python -m stackxray <folder>   -> scan that folder and open the report file directly
  python -m stackxray scan|app   -> the full CLI (V2 features)
"""

import os
import sys


def main() -> int:
    args = sys.argv[1:]
    if not args:                                   # no args -> friendly browser form
        from .webapp.agentify_app import serve
        serve()
        return 0
    from .v1 import is_git_url
    if os.path.isdir(args[0]) or is_git_url(args[0]):   # a folder OR a Git URL -> scan + open
        from .v1 import run_and_open
        run_and_open(args[0])
        return 0
    from .cli import main as cli_main               # scan / app / agentify subcommands
    return cli_main(args)


if __name__ == "__main__":
    raise SystemExit(main())
