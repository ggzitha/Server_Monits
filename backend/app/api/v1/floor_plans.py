from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.api.deps import get_db, require_permission
from backend.app.core.audit import record_audit_log
from backend.app.db.models.floor_plan import FloorPlan, Room
from backend.app.db.models.placed_object import PlacedObject

router = APIRouter(prefix="/plans", tags=["floor-plans"])


class RoomDTO(BaseModel):
    id: Optional[str] = None
    name: str = "Server Room"
    polygon_points: List[List[float]] = []  # [[x0, z0], [x1, z1], ...]
    wall_height_m: float = 3.0
    wall_thickness_m: float = 0.2
    floor_color: str = "#0e1424"
    wall_color: str = "#00f0ff"


class PlacedObjectDTO(BaseModel):
    id: Optional[str] = None
    room_id: Optional[str] = None
    object_type: str = "wall"  # wall, door, window, rack, sensor, etc.
    name: str = "Object"
    position_x: float = 0.0
    position_y: float = 0.0
    position_z: float = 0.0
    rotation_x: float = 0.0
    rotation_y: float = 0.0
    rotation_z: float = 0.0
    scale_x: float = 1.0
    scale_y: float = 1.0
    scale_z: float = 1.0
    properties: Dict[str, Any] = {}


class CreateFloorPlanRequest(BaseModel):
    name: str
    site_name: str = "Main Data Center"
    level_index: int = 0
    grid_size_meters: float = 0.5
    scale_ratio: float = 1.0
    metadata_json: Dict[str, Any] = {}


class UpdateFloorPlanRequest(BaseModel):
    name: Optional[str] = None
    site_name: Optional[str] = None
    level_index: Optional[int] = None
    grid_size_meters: Optional[float] = None
    scale_ratio: Optional[float] = None
    metadata_json: Optional[Dict[str, Any]] = None
    rooms: Optional[List[RoomDTO]] = None
    objects: Optional[List[PlacedObjectDTO]] = None


class ImportFloorPlanRequest(BaseModel):
    plan: CreateFloorPlanRequest
    rooms: List[RoomDTO] = []
    objects: List[PlacedObjectDTO] = []


@router.get("", dependencies=[Depends(require_permission("plans:read"))])
async def list_floor_plans(
    site: Optional[str] = None,
    level: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    """List all floor plans with summaries."""
    stmt = select(FloorPlan).options(
        selectinload(FloorPlan.rooms),
        selectinload(FloorPlan.objects),
    ).order_by(FloorPlan.site_name.asc(), FloorPlan.level_index.asc())

    if site:
        stmt = stmt.where(FloorPlan.site_name == site)
    if level is not None:
        stmt = stmt.where(FloorPlan.level_index == level)

    res = await db.execute(stmt)
    plans = res.scalars().all()

    return [
        {
            "id": p.id,
            "name": p.name,
            "site_name": p.site_name,
            "level_index": p.level_index,
            "grid_size_meters": p.grid_size_meters,
            "scale_ratio": p.scale_ratio,
            "room_count": len(p.rooms),
            "object_count": len(p.objects),
            "created_at": p.created_at,
            "updated_at": p.updated_at,
        }
        for p in plans
    ]


@router.post("", dependencies=[Depends(require_permission("plans:write"))])
async def create_floor_plan(
    req: CreateFloorPlanRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Create a new empty floor plan."""
    plan = FloorPlan(
        name=req.name,
        site_name=req.site_name,
        level_index=req.level_index,
        grid_size_meters=req.grid_size_meters,
        scale_ratio=req.scale_ratio,
        metadata_json=req.metadata_json,
    )
    db.add(plan)
    await db.commit()
    await db.refresh(plan)

    await record_audit_log(
        db, "PLAN_CREATE", resource_type="floor_plans", resource_id=plan.id,
        details={"name": plan.name, "site": plan.site_name, "level": plan.level_index},
        request=request,
    )

    return {
        "id": plan.id,
        "name": plan.name,
        "site_name": plan.site_name,
        "level_index": plan.level_index,
        "grid_size_meters": plan.grid_size_meters,
        "scale_ratio": plan.scale_ratio,
    }


@router.get("/{plan_id}", dependencies=[Depends(require_permission("plans:read"))])
async def get_floor_plan(plan_id: str, db: AsyncSession = Depends(get_db)):
    """Fetch complete floor plan with its rooms and placed objects."""
    stmt = select(FloorPlan).options(
        selectinload(FloorPlan.rooms),
        selectinload(FloorPlan.objects),
    ).where(FloorPlan.id == plan_id)
    res = await db.execute(stmt)
    plan = res.scalar_one_or_none()

    if not plan:
        raise HTTPException(status_code=404, detail="Floor plan not found")

    return {
        "id": plan.id,
        "name": plan.name,
        "site_name": plan.site_name,
        "level_index": plan.level_index,
        "grid_size_meters": plan.grid_size_meters,
        "scale_ratio": plan.scale_ratio,
        "metadata": plan.metadata_json,
        "created_at": plan.created_at,
        "updated_at": plan.updated_at,
        "rooms": [
            {
                "id": r.id,
                "name": r.name,
                "polygon_points": r.polygon_points,
                "wall_height_m": r.wall_height_m,
                "wall_thickness_m": r.wall_thickness_m,
                "floor_color": r.floor_color,
                "wall_color": r.wall_color,
            }
            for r in plan.rooms
        ],
        "objects": [
            {
                "id": o.id,
                "room_id": o.room_id,
                "object_type": o.object_type,
                "name": o.name,
                "position": {"x": o.position_x, "y": o.position_y, "z": o.position_z},
                "rotation": {"x": o.rotation_x, "y": o.rotation_y, "z": o.rotation_z},
                "scale": {"x": o.scale_x, "y": o.scale_y, "z": o.scale_z},
                "properties": o.properties,
            }
            for o in plan.objects
        ],
    }


@router.put("/{plan_id}", dependencies=[Depends(require_permission("plans:write"))])
async def update_floor_plan(
    plan_id: str,
    req: UpdateFloorPlanRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Save and update complete floor plan layout including rooms and placed objects."""
    stmt = select(FloorPlan).options(
        selectinload(FloorPlan.rooms),
        selectinload(FloorPlan.objects),
    ).where(FloorPlan.id == plan_id)
    res = await db.execute(stmt)
    plan = res.scalar_one_or_none()

    if not plan:
        raise HTTPException(status_code=404, detail="Floor plan not found")

    if req.name is not None:
        plan.name = req.name
    if req.site_name is not None:
        plan.site_name = req.site_name
    if req.level_index is not None:
        plan.level_index = req.level_index
    if req.grid_size_meters is not None:
        plan.grid_size_meters = req.grid_size_meters
    if req.scale_ratio is not None:
        plan.scale_ratio = req.scale_ratio
    if req.metadata_json is not None:
        plan.metadata_json = req.metadata_json

    # Synchronize rooms if supplied
    if req.rooms is not None:
        plan.rooms.clear()
        for r_dto in req.rooms:
            room_kwargs = {
                "name": r_dto.name,
                "polygon_points": r_dto.polygon_points,
                "wall_height_m": r_dto.wall_height_m,
                "wall_thickness_m": r_dto.wall_thickness_m,
                "floor_color": r_dto.floor_color,
                "wall_color": r_dto.wall_color,
            }
            if r_dto.id:
                room_kwargs["id"] = r_dto.id
            plan.rooms.append(Room(**room_kwargs))

    # Synchronize placed objects if supplied
    if req.objects is not None:
        plan.objects.clear()
        for o_dto in req.objects:
            obj_kwargs = {
                "room_id": o_dto.room_id,
                "object_type": o_dto.object_type,
                "name": o_dto.name,
                "position_x": o_dto.position_x,
                "position_y": o_dto.position_y,
                "position_z": o_dto.position_z,
                "rotation_x": o_dto.rotation_x,
                "rotation_y": o_dto.rotation_y,
                "rotation_z": o_dto.rotation_z,
                "scale_x": o_dto.scale_x,
                "scale_y": o_dto.scale_y,
                "scale_z": o_dto.scale_z,
                "properties": o_dto.properties,
            }
            if o_dto.id:
                obj_kwargs["id"] = o_dto.id
            plan.objects.append(PlacedObject(**obj_kwargs))

    await db.commit()
    await record_audit_log(
        db, "PLAN_UPDATE", resource_type="floor_plans", resource_id=plan.id,
        details={"name": plan.name, "room_count": len(plan.rooms), "object_count": len(plan.objects)},
        request=request,
    )

    return {"success": True, "message": "Floor plan saved successfully"}


@router.delete("/{plan_id}", dependencies=[Depends(require_permission("plans:write"))])
async def delete_floor_plan(
    plan_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Delete a floor plan and all associated rooms/objects."""
    stmt = select(FloorPlan).where(FloorPlan.id == plan_id)
    res = await db.execute(stmt)
    plan = res.scalar_one_or_none()

    if not plan:
        raise HTTPException(status_code=404, detail="Floor plan not found")

    plan_name = plan.name
    await db.delete(plan)
    await db.commit()

    await record_audit_log(
        db, "PLAN_DELETE", resource_type="floor_plans", resource_id=plan_id,
        details={"name": plan_name}, request=request,
    )

    return {"success": True, "message": "Floor plan deleted"}


@router.post("/{plan_id}/export", dependencies=[Depends(require_permission("plans:read"))])
async def export_floor_plan(plan_id: str, db: AsyncSession = Depends(get_db)):
    """Export floor plan as a portable JSON bundle."""
    stmt = select(FloorPlan).options(
        selectinload(FloorPlan.rooms),
        selectinload(FloorPlan.objects),
    ).where(FloorPlan.id == plan_id)
    res = await db.execute(stmt)
    plan = res.scalar_one_or_none()

    if not plan:
        raise HTTPException(status_code=404, detail="Floor plan not found")

    return {
        "version": "1.0",
        "plan": {
            "name": plan.name,
            "site_name": plan.site_name,
            "level_index": plan.level_index,
            "grid_size_meters": plan.grid_size_meters,
            "scale_ratio": plan.scale_ratio,
            "metadata_json": plan.metadata_json,
        },
        "rooms": [
            {
                "id": r.id,
                "name": r.name,
                "polygon_points": r.polygon_points,
                "wall_height_m": r.wall_height_m,
                "wall_thickness_m": r.wall_thickness_m,
                "floor_color": r.floor_color,
                "wall_color": r.wall_color,
            }
            for r in plan.rooms
        ],
        "objects": [
            {
                "id": o.id,
                "room_id": o.room_id,
                "object_type": o.object_type,
                "name": o.name,
                "position_x": o.position_x,
                "position_y": o.position_y,
                "position_z": o.position_z,
                "rotation_x": o.rotation_x,
                "rotation_y": o.rotation_y,
                "rotation_z": o.rotation_z,
                "scale_x": o.scale_x,
                "scale_y": o.scale_y,
                "scale_z": o.scale_z,
                "properties": o.properties,
            }
            for o in plan.objects
        ],
    }


@router.post("/import", dependencies=[Depends(require_permission("plans:write"))])
async def import_floor_plan(
    req: ImportFloorPlanRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Import a floor plan from a JSON bundle."""
    new_plan = FloorPlan(
        name=req.plan.name,
        site_name=req.plan.site_name,
        level_index=req.plan.level_index,
        grid_size_meters=req.plan.grid_size_meters,
        scale_ratio=req.plan.scale_ratio,
        metadata_json=req.plan.metadata_json,
    )
    for r in req.rooms:
        new_plan.rooms.append(Room(
            name=r.name,
            polygon_points=r.polygon_points,
            wall_height_m=r.wall_height_m,
            wall_thickness_m=r.wall_thickness_m,
            floor_color=r.floor_color,
            wall_color=r.wall_color,
        ))
    for o in req.objects:
        new_plan.objects.append(PlacedObject(
            room_id=o.room_id,
            object_type=o.object_type,
            name=o.name,
            position_x=o.position_x,
            position_y=o.position_y,
            position_z=o.position_z,
            rotation_x=o.rotation_x,
            rotation_y=o.rotation_y,
            rotation_z=o.rotation_z,
            scale_x=o.scale_x,
            scale_y=o.scale_y,
            scale_z=o.scale_z,
            properties=o.properties,
        ))

    db.add(new_plan)
    await db.commit()
    await db.refresh(new_plan)

    await record_audit_log(
        db, "PLAN_IMPORT", resource_type="floor_plans", resource_id=new_plan.id,
        details={"name": new_plan.name}, request=request,
    )

    return {"success": True, "id": new_plan.id, "message": "Floor plan imported successfully"}

