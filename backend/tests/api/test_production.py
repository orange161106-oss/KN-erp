    import pytest
from fastapi.testclient import TestClient
from uuid import uuid4

from app.main import app
from app.security.dependencies import get_current_user
from app.schemas.auth import CurrentUser

mock_user = CurrentUser(
    id=uuid4(), 
    email="test@kn.com", 
    username="testuser",
    is_active=True, 
    is_superuser=False,
    roles=[],
    permissions=[]
)

def override_get_current_user():
    return mock_user

@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c

# ==========================
# 1. UNAUTHORIZED MUTATION
# ==========================
def test_unauthorized_mutation(client):
    app.dependency_overrides.clear()
    
    response = client.post("/api/v1/plants", json={"name": f"Secret Plant {uuid4()}"})
    assert response.status_code in [401, 403] 

# ==========================
# 2. CRUD, UNIQUENESS & INACTIVATION (SOFT DELETE)
# ==========================
def test_plant_crud_and_inactivation(client):
    app.dependency_overrides[get_current_user] = override_get_current_user
    
    # CREATE
    plant_data = {"name": f"Test Plant {uuid4()}", "location": "Chennai"}
    create_res = client.post("/api/v1/plants", json=plant_data)
    assert create_res.status_code == 201
    plant_id = create_res.json()["id"]

    # UNIQUENESS (Duplicate Name)
    duplicate_res = client.post("/api/v1/plants", json=plant_data)
    assert duplicate_res.status_code == 400

    # READ
    get_res = client.get("/api/v1/plants")
    assert get_res.status_code == 200
    assert any(p["id"] == plant_id for p in get_res.json())

    # UPDATE (Using a UUID so it never collides with past test runs)
    updated_name = f"Updated Plant {uuid4()}"
    update_res = client.put(f"/api/v1/plants/{plant_id}", json={"name": updated_name})
    assert update_res.status_code == 200
    assert update_res.json()["name"] == updated_name

    # INACTIVATION (Soft Delete)
    del_res = client.delete(f"/api/v1/plants/{plant_id}")
    assert del_res.status_code == 204

    # Verify Inactivation
    get_res_after_del = client.get("/api/v1/plants")
    assert not any(p["id"] == plant_id for p in get_res_after_del.json())

# ==========================
# 3. ROUTE SEQUENCE UNIQUENESS
# ==========================
def test_route_sequence_uniqueness(client):
    app.dependency_overrides[get_current_user] = override_get_current_user
    
    route_data = {
        "name": f"Test Route {uuid4()}",
        "steps": [
            {"sequence_order": 1, "process_id": str(uuid4())},
            {"sequence_order": 1, "process_id": str(uuid4())}
        ]
    }
    
    response = client.post("/api/v1/routes", json=route_data)
    assert response.status_code == 400