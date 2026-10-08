from app.security.permissions import require_permissions
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from sqlalchemy import select

# ADJUST THIS IMPORT based on your project's auth setup to secure the routes
from app.security.dependencies import get_current_user

from app.models.production import Plant, Process, Route, RouteStep
from app.schemas.production import (
    PlantCreate, PlantUpdate, PlantResponse,
    ProcessCreate, ProcessUpdate, ProcessResponse,
    RouteCreate, RouteUpdate, RouteResponse
)

# Securing the entire router with the auth dependency
router = APIRouter(tags=["Production Masters"], dependencies=[Depends(get_current_user)])

def get_db(request: Request):
    with request.app.state.session_factory() as session:
        yield session

# ==========================
# PLANT ENDPOINTS
# ==========================
@router.post("/plants", response_model=PlantResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_permissions('masters.write'))])
def create_plant(plant_in: PlantCreate, db: Session = Depends(get_db)):
    db_plant = db.scalar(select(Plant).where(Plant.name == plant_in.name))
    if db_plant:
        raise HTTPException(status_code=400, detail="Plant already exists.")
    new_plant = Plant(**plant_in.model_dump())
    db.add(new_plant)
    db.commit()
    db.refresh(new_plant)
    return new_plant

@router.get("/plants", response_model=list[PlantResponse], dependencies=[Depends(require_permissions('masters.read'))])
def get_plants(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return db.scalars(select(Plant).where(Plant.is_active == True).offset(skip).limit(limit)).all()

@router.get("/plants/{plant_id}", response_model=PlantResponse, dependencies=[Depends(require_permissions('masters.read'))])
def get_plant(plant_id: UUID, db: Session = Depends(get_db)):
    plant = db.get(Plant, plant_id)
    if not plant:
        raise HTTPException(status_code=404, detail="Plant not found")
    return plant

@router.put("/plants/{plant_id}", response_model=PlantResponse, dependencies=[Depends(require_permissions('masters.write'))])
def update_plant(plant_id: UUID, plant_in: PlantUpdate, db: Session = Depends(get_db)):
    plant = db.get(Plant, plant_id)
    if not plant:
        raise HTTPException(status_code=404, detail="Plant not found")
    for field, value in plant_in.model_dump(exclude_unset=True).items():
        setattr(plant, field, value)
    db.commit()
    db.refresh(plant)
    return plant

@router.delete("/plants/{plant_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_permissions('masters.write'))])
def delete_plant(plant_id: UUID, db: Session = Depends(get_db)):
    plant = db.get(Plant, plant_id)
    if not plant:
        raise HTTPException(status_code=404, detail="Plant not found")
    plant.is_active = False # Soft delete compliance
    db.commit()

# ==========================
# PROCESS ENDPOINTS
# ==========================
@router.post("/processes", response_model=ProcessResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_permissions('masters.write'))])
def create_process(process_in: ProcessCreate, db: Session = Depends(get_db)):
    db_process = db.scalar(select(Process).where(Process.name == process_in.name))
    if db_process:
        raise HTTPException(status_code=400, detail="Process already exists.")
    new_process = Process(**process_in.model_dump())
    db.add(new_process)
    db.commit()
    db.refresh(new_process)
    return new_process

@router.get("/processes", response_model=list[ProcessResponse], dependencies=[Depends(require_permissions('masters.read'))])
def get_processes(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return db.scalars(select(Process).where(Process.is_active == True).offset(skip).limit(limit)).all()

@router.put("/processes/{process_id}", response_model=ProcessResponse, dependencies=[Depends(require_permissions('masters.write'))])
def update_process(process_id: UUID, process_in: ProcessUpdate, db: Session = Depends(get_db)):
    process = db.get(Process, process_id)
    if not process:
        raise HTTPException(status_code=404, detail="Process not found")
    for field, value in process_in.model_dump(exclude_unset=True).items():
        setattr(process, field, value)
    db.commit()
    db.refresh(process)
    return process

@router.delete("/processes/{process_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_permissions('masters.write'))])
def delete_process(process_id: UUID, db: Session = Depends(get_db)):
    process = db.get(Process, process_id)
    if not process:
        raise HTTPException(status_code=404, detail="Process not found")
    process.is_active = False # Soft delete compliance
    db.commit()

# ==========================
# ROUTE ENDPOINTS
# ==========================
@router.post("/routes", response_model=RouteResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_permissions('masters.write'))])
def create_route(route_in: RouteCreate, db: Session = Depends(get_db)):
    db_route = db.scalar(select(Route).where(Route.name == route_in.name))
    if db_route:
        raise HTTPException(status_code=400, detail="Route already exists.")
    
    route_data = route_in.model_dump(exclude={"steps"} if hasattr(route_in, "steps") else None)
    new_route = Route(**route_data)
    
    db.add(new_route)
    db.flush() 

    if hasattr(route_in, "steps") and route_in.steps:
        # Enforce sequence uniqueness internally
        used_sequences = set()
        for step_in in route_in.steps:
            if step_in.sequence_order in used_sequences:
                raise HTTPException(status_code=400, detail="Duplicate sequence numbers in route steps.")
            used_sequences.add(step_in.sequence_order)
            new_step = RouteStep(**step_in.model_dump(), route_id=new_route.id)
            db.add(new_step)

    db.commit()
    db.refresh(new_route)
    return new_route

@router.get("/routes", response_model=list[RouteResponse], dependencies=[Depends(require_permissions('masters.read'))])
def get_routes(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return db.scalars(select(Route).where(Route.is_active == True).offset(skip).limit(limit)).all()

@router.get("/routes/{route_id}", response_model=RouteResponse, dependencies=[Depends(require_permissions('masters.read'))])
def get_route(route_id: UUID, db: Session = Depends(get_db)):
    route = db.get(Route, route_id)
    if not route:
        raise HTTPException(status_code=404, detail="Route not found")
    return route

@router.put("/routes/{route_id}", response_model=RouteResponse, dependencies=[Depends(require_permissions('masters.write'))])
def update_route(route_id: UUID, route_in: RouteUpdate, db: Session = Depends(get_db)):
    route = db.get(Route, route_id)
    if not route:
        raise HTTPException(status_code=404, detail="Route not found")
    
    update_data = route_in.model_dump(exclude_unset=True, exclude={"steps"})
    for field, value in update_data.items():
        setattr(route, field, value)
    
    # If steps are provided, replace existing steps
    if hasattr(route_in, "steps") and route_in.steps is not None:
        # Delete old steps
        for step in route.steps:
            db.delete(step)
        
        used_sequences = set()
        for step_in in route_in.steps:
            if step_in.sequence_order in used_sequences:
                raise HTTPException(status_code=400, detail="Duplicate sequence numbers.")
            used_sequences.add(step_in.sequence_order)
            new_step = RouteStep(**step_in.model_dump(), route_id=route.id)
            db.add(new_step)

    db.commit()
    db.refresh(route)
    return route

@router.delete("/routes/{route_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_permissions('masters.write'))])
def delete_route(route_id: UUID, db: Session = Depends(get_db)):
    route = db.get(Route, route_id)
    if not route:
        raise HTTPException(status_code=404, detail="Route not found")
    route.is_active = False # Soft delete compliance
    db.commit()