"""
Re-exports each router's APIRouter instance so main.py can do:
    from routers import upload, process, records, conflicts, share, abha
"""

from routers.upload    import router as upload
from routers.process   import router as process
from routers.records   import router as records
from routers.conflicts import router as conflicts
from routers.share     import router as share
from routers.abha      import router as abha
from routers.profile   import router as profile

__all__ = ["upload", "process", "records", "conflicts", "share", "abha", "profile"]
