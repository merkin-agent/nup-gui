"""Package entry point used by ``python -m nup`` and frozen builds."""

from .cli import main

raise SystemExit(main())
