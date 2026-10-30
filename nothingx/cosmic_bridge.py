import os
import sys
from pathlib import Path


def main():
    executable = Path(__file__).resolve().parent / "bin/nothingx-core"
    os.execv(executable, [str(executable), "--auto"])


if __name__ == "__main__":
    sys.exit(main())
