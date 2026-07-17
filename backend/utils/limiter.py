"""
Shared slowapi Limiter instance.

Router modules import `limiter` from here (not from main) to avoid a circular
import: main.py imports the routers, so a router importing `limiter` from
main would import main.py itself, which hasn't finished defining `app` yet.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
