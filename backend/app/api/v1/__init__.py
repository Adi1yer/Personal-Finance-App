from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_current_profile
from app.api.v1 import (
    accounts,
    advisor,
    alerts,
    auth,
    categories,
    category_rules,
    duplicates,
    entries,
    goals,
    google_drive,
    institutions,
    overview,
    plaid,
    reconcile,
    register,
    reports,
    settings,
    setup,
    transactions,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(setup.router)
api_router.include_router(plaid.browser_router)
api_router.include_router(google_drive.browser_router)

protected = APIRouter(dependencies=[Depends(get_current_profile)])
protected.include_router(accounts.router)
protected.include_router(institutions.router)
protected.include_router(categories.router)
protected.include_router(transactions.router)
protected.include_router(register.router)
protected.include_router(entries.router)
protected.include_router(category_rules.router)
protected.include_router(duplicates.router)
protected.include_router(reconcile.router)
protected.include_router(reports.router)
protected.include_router(overview.router)
protected.include_router(plaid.router)
protected.include_router(goals.router)
protected.include_router(advisor.router)
protected.include_router(alerts.router)
protected.include_router(settings.router)
protected.include_router(google_drive.router)
api_router.include_router(protected)
