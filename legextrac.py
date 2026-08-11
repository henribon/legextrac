"""Ponto de entrada do executavel.

O PyInstaller precisa de um script, nao de um modulo (-m app.gui nao serve).
"""

import sys

from app.gui import main

if __name__ == "__main__":
    sys.exit(main())
