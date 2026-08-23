"""HTTP routes for the POWER Web UI."""

from .auth import router as auth_router
from .dashboard import router as dashboard_router
from .decisions import router as decisions_router
from .federation import router as federation_router
from .graph import router as graph_router
from .notes import router as notes_router
from .receipts import router as receipts_router
from .search import router as search_router
from .tasks import router as tasks_router

__all__ = [
    "auth_router",
    "dashboard_router",
    "decisions_router",
    "federation_router",
    "graph_router",
    "notes_router",
    "receipts_router",
    "search_router",
    "tasks_router",
]
