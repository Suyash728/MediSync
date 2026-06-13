"""
Supabase service-role client singleton.

All backend DB operations use the SERVICE ROLE key, which bypasses Row-Level
Security.  This is intentional — the backend enforces ownership checks itself
(e.g. "does this patient_id match the JWT?").  The service key must NEVER be
exposed to the browser.
"""

import functools
from supabase import Client, create_client
from utils.config import settings


@functools.lru_cache(maxsize=1)
def get_supabase() -> Client:
    """Return the module-level Supabase client (created once, reused).

    Using lru_cache(maxsize=1) means the client is created on first call and
    reused for the lifetime of the process — avoids repeated network handshakes.
    """
    return create_client(settings.supabase_url, settings.supabase_service_key)
