"""WSGI entry point used by cPanel's Setup Python App / Passenger."""
import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from app import app as application  # noqa: E402
