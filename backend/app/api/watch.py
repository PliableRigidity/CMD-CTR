from fastapi import APIRouter, Depends, HTTPException

from backend.app.models.watch_officer import WatchAlert, WatchAlertCreate
from backend.app.services.watch_service import WatchService

router = APIRouter(tags=["watch"])

_service: WatchService | None = None


def _get_service() -> WatchService:
    global _service
    if _service is None:
        _service = WatchService()
    return _service


@router.get("/watch", response_model=list[WatchAlert])
async def list_alerts(
    include_dismissed: bool = False,
    svc: WatchService = Depends(_get_service),
):
    return svc.list_alerts(include_dismissed)


@router.post("/watch", response_model=WatchAlert, status_code=201)
async def create_alert(data: WatchAlertCreate, svc: WatchService = Depends(_get_service)):
    return svc.create_alert(data)


@router.post("/watch/{alert_id}/dismiss")
async def dismiss_alert(alert_id: str, svc: WatchService = Depends(_get_service)):
    ok = svc.dismiss_alert(alert_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"id": alert_id, "dismissed": True}


@router.delete("/watch/{alert_id}", status_code=204)
async def delete_alert(alert_id: str, svc: WatchService = Depends(_get_service)):
    ok = svc.delete_alert(alert_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Alert not found")
