from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["dashboard"])

TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "dashboard.html"


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    return HTMLResponse(TEMPLATE.read_text())
