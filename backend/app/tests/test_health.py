from sqlalchemy.exc import OperationalError


def test_health_success(client, database_session):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}
    database_session.execute.assert_called_once()


def test_database_failure_is_sanitized(client, database_session):
    database_session.execute.side_effect = OperationalError(
        "SELECT 1", {}, Exception("password=do_not_expose"),
    )
    response = client.get("/api/v1/health")
    assert response.status_code == 503
    assert response.json() == {
        "code": "DATABASE_UNAVAILABLE", "message": "Database is unavailable.", "details": {},
    }
    assert "do_not_expose" not in response.text


def test_health_openapi_contract(client):
    operation = client.get("/openapi.json").json()["paths"]["/api/v1/health"]["get"]
    assert "200" in operation["responses"]
    assert "503" in operation["responses"]
