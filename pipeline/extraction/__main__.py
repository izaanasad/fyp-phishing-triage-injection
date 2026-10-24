"""Enable `python -m extraction <file> [--json]`."""
import sys

from .extract import _main

if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
