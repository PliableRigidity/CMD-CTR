"""Hardware Operations REST API — inventory, projects, project-part links, orders."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from backend.app.services.hardware_service import HardwareService

router = APIRouter(prefix="/hardware", tags=["hardware"])

_svc: HardwareService | None = None


def _get_svc() -> HardwareService:
    global _svc
    if _svc is None:
        _svc = HardwareService()
    return _svc


# ── Request models ────────────────────────────────────────────────────────────

class PartCreate(BaseModel):
    name: str
    category: str = "misc"
    quantity: int = 1
    subcategory: str = ""
    manufacturer: str = ""
    part_number: str = ""
    location: str = ""
    notes: str = ""
    datasheet_url: str = ""
    status: str = "in-stock"


class PartUpdate(BaseModel):
    name: str | None = None
    category: str | None = None
    subcategory: str | None = None
    quantity: int | None = None
    status: str | None = None
    location: str | None = None
    manufacturer: str | None = None
    part_number: str | None = None
    notes: str | None = None
    datasheet_url: str | None = None


class ProjectCreate(BaseModel):
    name: str
    description: str = ""
    status: str = "active"
    priority: str = "normal"
    notes: str = ""


class ProjectUpdate(BaseModel):
    name: str | None = None
    status: str | None = None
    description: str | None = None
    priority: str | None = None
    notes: str | None = None


class LinkCreate(BaseModel):
    part_id: str
    quantity_required: int = 1
    is_required: int = 1
    notes: str = ""


class OrderCreate(BaseModel):
    part_name: str
    vendor: str = ""
    quantity: int = 1
    notes: str = ""
    status: str = "ordered"
    expected_delivery: str = ""


class PartThresholdUpdate(BaseModel):
    threshold: int


class OrderStatusUpdate(BaseModel):
    status: str


class ImportRequest(BaseModel):
    path: str
    source_type: str = Field(default="auto", pattern="^(auto|bom|inventory)$")
    project: str = ""


class HardwareAssistantRequest(BaseModel):
    message: str
    pending_action: dict | None = None


class VisionDetectionItem(BaseModel):
    name: str
    quantity: int = 1
    category: str = "misc"
    subcategory: str = ""
    notes: str = ""


class VisionApplyRequest(BaseModel):
    detections: list[VisionDetectionItem]


# ── Summary ───────────────────────────────────────────────────────────────────

@router.get("/summary")
def get_summary(svc: HardwareService = Depends(_get_svc)):
    return svc.summary()


# ── Inventory ─────────────────────────────────────────────────────────────────

@router.get("/inventory")
def list_inventory(
    category: str = "",
    search: str = "",
    svc: HardwareService = Depends(_get_svc),
):
    return svc.list_parts(category=category, search=search)


@router.post("/inventory", status_code=201)
def create_part(data: PartCreate, svc: HardwareService = Depends(_get_svc)):
    if not data.name.strip():
        raise HTTPException(status_code=400, detail="name is required")
    return svc.add_part(
        name=data.name,
        category=data.category,
        quantity=data.quantity,
        subcategory=data.subcategory,
        manufacturer=data.manufacturer,
        part_number=data.part_number,
        location=data.location,
        notes=data.notes,
        datasheet_url=data.datasheet_url,
        status=data.status,
    )


@router.get("/inventory/{part_id}")
def get_part(part_id: str, svc: HardwareService = Depends(_get_svc)):
    part = svc.get_part_by_id(part_id)
    if not part:
        raise HTTPException(status_code=404, detail="Part not found")
    return part


@router.put("/inventory/{part_id}")
def update_part(part_id: str, data: PartUpdate, svc: HardwareService = Depends(_get_svc)):
    part = svc.get_part_by_id(part_id)
    if not part:
        raise HTTPException(status_code=404, detail="Part not found")
    return svc.update_part(part_id, **data.model_dump(exclude_unset=True))


@router.delete("/inventory/{part_id}", status_code=204)
def delete_part(part_id: str, svc: HardwareService = Depends(_get_svc)):
    ok = svc.delete_part(part_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Part not found")


@router.get("/categories")
def get_categories(svc: HardwareService = Depends(_get_svc)):
    return svc.category_summary()


# ── Projects ──────────────────────────────────────────────────────────────────

@router.get("/projects")
def list_projects(status: str = "", svc: HardwareService = Depends(_get_svc)):
    return svc.list_projects(status=status)


@router.post("/projects", status_code=201)
def create_project(data: ProjectCreate, svc: HardwareService = Depends(_get_svc)):
    if not data.name.strip():
        raise HTTPException(status_code=400, detail="name is required")
    return svc.create_project(
        name=data.name,
        description=data.description,
        status=data.status,
        priority=data.priority,
        notes=data.notes,
    )


@router.get("/projects/{project_id}")
def get_project(project_id: str, svc: HardwareService = Depends(_get_svc)):
    project = svc.get_project_with_parts(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.put("/projects/{project_id}")
def update_project(project_id: str, data: ProjectUpdate, svc: HardwareService = Depends(_get_svc)):
    project = svc.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return svc.update_project(project_id, **data.model_dump(exclude_unset=True))


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: str, svc: HardwareService = Depends(_get_svc)):
    ok = svc.delete_project(project_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Project not found")


# ── Project-Part Links ────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/parts")
def list_project_parts(project_id: str, svc: HardwareService = Depends(_get_svc)):
    project = svc.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return svc.get_project_parts(project_id)


@router.post("/projects/{project_id}/parts", status_code=201)
def assign_part(project_id: str, data: LinkCreate, svc: HardwareService = Depends(_get_svc)):
    project = svc.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    part = svc.get_part_by_id(data.part_id)
    if not part:
        raise HTTPException(status_code=404, detail="Part not found")
    return svc.assign_part_to_project(
        project_id, data.part_id, data.quantity_required, data.notes, data.is_required
    )


@router.delete("/projects/{project_id}/parts/{part_id}", status_code=204)
def unassign_part(project_id: str, part_id: str, svc: HardwareService = Depends(_get_svc)):
    ok = svc.unassign_part_from_project(project_id, part_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Link not found")


@router.get("/inventory/{part_id}/projects")
def get_part_projects(part_id: str, svc: HardwareService = Depends(_get_svc)):
    part = svc.get_part_by_id(part_id)
    if not part:
        raise HTTPException(status_code=404, detail="Part not found")
    return svc.get_part_projects(part_id)


# ── Orders ────────────────────────────────────────────────────────────────────

@router.get("/orders")
def list_orders(status: str = "", svc: HardwareService = Depends(_get_svc)):
    return svc.list_orders(status=status)


@router.post("/orders", status_code=201)
def create_order(data: OrderCreate, svc: HardwareService = Depends(_get_svc)):
    if not data.part_name.strip():
        raise HTTPException(status_code=400, detail="part_name is required")
    return svc.add_order(
        part_name=data.part_name,
        vendor=data.vendor,
        quantity=data.quantity,
        notes=data.notes,
        status=data.status,
        expected_delivery=data.expected_delivery,
    )


@router.get("/orders/{order_id}")
def get_order(order_id: str, svc: HardwareService = Depends(_get_svc)):
    order = svc.get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@router.patch("/orders/{order_id}/status")
def update_order_status(
    order_id: str, data: OrderStatusUpdate, svc: HardwareService = Depends(_get_svc)
):
    order = svc.get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    updated = svc.update_order_status(order_id, data.status)
    if not updated:
        raise HTTPException(status_code=400, detail=f"Invalid status: {data.status}")
    return updated


@router.delete("/orders/{order_id}", status_code=204)
def delete_order(order_id: str, svc: HardwareService = Depends(_get_svc)):
    ok = svc.delete_order(order_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Order not found")


# ── Order receive ─────────────────────────────────────────────────────────────

@router.post("/orders/{order_id}/receive")
def receive_order(order_id: str, svc: HardwareService = Depends(_get_svc)):
    order = svc.get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    result = svc.receive_order(order_id)
    if not result:
        raise HTTPException(status_code=500, detail="Failed to receive order")
    return result


# ── Inventory threshold ────────────────────────────────────────────────────────

@router.patch("/inventory/{part_id}/threshold")
def set_reorder_threshold(part_id: str, data: PartThresholdUpdate, svc: HardwareService = Depends(_get_svc)):
    part = svc.get_part_by_id(part_id)
    if not part:
        raise HTTPException(status_code=404, detail="Part not found")
    return svc.update_part(part_id, reorder_threshold=data.threshold)


# ── Project Intelligence (Phase 12B) ──────────────────────────────────────────

@router.get("/intelligence/readiness")
def get_all_readiness(svc: HardwareService = Depends(_get_svc)):
    return svc.get_all_readiness()


@router.get("/intelligence/readiness/{project_id}")
def get_project_readiness(project_id: str, svc: HardwareService = Depends(_get_svc)):
    r = svc.get_build_readiness(project_id)
    if not r:
        raise HTTPException(status_code=404, detail="Project not found")
    return r


@router.get("/intelligence/missing")
def get_missing_parts(svc: HardwareService = Depends(_get_svc)):
    return svc.get_all_missing_parts()


@router.get("/intelligence/blocked")
def get_blocked(svc: HardwareService = Depends(_get_svc)):
    return svc.get_blocked_projects()


@router.get("/intelligence/recommendations")
def get_recommendations(svc: HardwareService = Depends(_get_svc)):
    return svc.get_order_recommendations()


@router.get("/intelligence/priority")
def get_priority_ranking(svc: HardwareService = Depends(_get_svc)):
    return svc.get_project_priorities()


@router.get("/intelligence/low-stock")
def get_low_stock(svc: HardwareService = Depends(_get_svc)):
    return svc.get_low_stock()


@router.get("/intelligence/after-delivery")
def get_after_delivery(svc: HardwareService = Depends(_get_svc)):
    return svc.get_after_delivery_readiness()


# ── Imports (Phase 12C) ─────────────────────────────────────────────────────

@router.get("/imports")
def list_imports(limit: int = 25, svc: HardwareService = Depends(_get_svc)):
    return svc.list_imports(limit=limit)


@router.post("/imports", status_code=201)
def import_hardware(data: ImportRequest, svc: HardwareService = Depends(_get_svc)):
    if not data.path.strip():
        raise HTTPException(status_code=400, detail="path is required")
    from backend.app.services.hardware_import_service import HardwareImportService
    try:
        return HardwareImportService(svc).import_file(
            data.path,
            source_type=data.source_type,
            project_name=data.project,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/imports/{import_id}/items")
def list_import_items(import_id: str, svc: HardwareService = Depends(_get_svc)):
    return svc.list_import_items(import_id)


@router.get("/projects/{project_id}/impact")
def get_inventory_impact(project_id: str, svc: HardwareService = Depends(_get_svc)):
    impact = svc.get_inventory_impact(project_id)
    if not impact:
        raise HTTPException(status_code=404, detail="Project not found")
    return impact


# ── Hardware Assistant (Phase 12D) ──────────────────────────────────────────

@router.post("/assistant")
def hardware_assistant(data: HardwareAssistantRequest, svc: HardwareService = Depends(_get_svc)):
    from backend.app.services.hardware_assistant_service import HardwareAssistantService
    return HardwareAssistantService(svc).handle(data.message, data.pending_action)


# ── Vision (Phase 12F) — disabled by default ─────────────────────────────────
# Set ENABLE_VISION_INVENTORY=true in .env to activate these endpoints.

_VISION_DISABLED = {"detail": "Vision inventory is disabled (ENABLE_VISION_INVENTORY=false)"}


@router.get("/vision/status")
def vision_status(svc: HardwareService = Depends(_get_svc)):
    from backend.config import ENABLE_VISION_INVENTORY
    if not ENABLE_VISION_INVENTORY:
        raise HTTPException(status_code=503, detail=_VISION_DISABLED["detail"])
    from backend.app.services.hardware_vision_service import HardwareVisionService
    return HardwareVisionService(svc).status()


@router.post("/vision/analyze")
async def vision_analyze(file: UploadFile = File(...), svc: HardwareService = Depends(_get_svc)):
    from backend.config import ENABLE_VISION_INVENTORY
    if not ENABLE_VISION_INVENTORY:
        raise HTTPException(status_code=503, detail=_VISION_DISABLED["detail"])
    content_type = file.content_type or "image/jpeg"
    if not (content_type.startswith("image/") or content_type == "application/octet-stream"):
        raise HTTPException(status_code=400, detail="File must be an image (JPEG, PNG, WebP)")
    image_bytes = await file.read()
    if len(image_bytes) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Image too large (max 20 MB)")
    if len(image_bytes) == 0:
        raise HTTPException(status_code=400, detail="Empty file received")
    from backend.app.services.hardware_vision_service import HardwareVisionService
    return HardwareVisionService(svc).analyze_image(
        image_bytes, content_type, filename=file.filename or ""
    )


@router.post("/vision/apply")
def vision_apply(data: VisionApplyRequest, svc: HardwareService = Depends(_get_svc)):
    from backend.config import ENABLE_VISION_INVENTORY
    if not ENABLE_VISION_INVENTORY:
        raise HTTPException(status_code=503, detail=_VISION_DISABLED["detail"])
    if not data.detections:
        raise HTTPException(status_code=400, detail="No detections provided")
    from backend.app.services.hardware_vision_service import HardwareVisionService
    return HardwareVisionService(svc).apply_detections([d.model_dump() for d in data.detections])
