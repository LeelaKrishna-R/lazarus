"""`python -m lazarus …` runs the same CLI as the `lazarus` script."""

import sys

from lazarus.cli import main

sys.exit(main())
