from fastapi import HTTPException
from pydantic import BaseModel


class ValidationPayload(BaseModel):
    count: int


def test_not_found_error_shape(client):
    response = client.get("/api/v1/missing")
    assert response.status_code == 404
    assert response.json() == {"code": "HTTP_ERROR", "message": "Not Found", "details": {}}


def test_validation_errors_do_not_echo_inputs(app, client):
    @app.post("/_test/validation")
    def validation(payload: ValidationPayload):
        return payload

    response = client.post("/_test/validation", json={"count": "sensitive_input"})
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert response.json()["details"]["errors"][0]["location"] == ["body", "count"]
    assert "sensitive_input" not in response.text


def test_http_error_preserves_authentication_header(app, client):
    @app.get("/_test/unauthorized")
    def unauthorized():
        raise HTTPException(401, "Authentication required.", headers={"WWW-Authenticate": "Bearer"})

    response = client.get("/_test/unauthorized")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json()["code"] == "HTTP_ERROR"


def test_unexpected_errors_do_not_echo_exception(app, client):
    @app.get("/_test/unexpected")
    def unexpected():
        raise RuntimeError("private_password")

    response = client.get("/_test/unexpected")
    assert response.status_code == 500
    assert response.json() == {
        "code": "INTERNAL_SERVER_ERROR", "message": "An unexpected error occurred.", "details": {},
    }
    assert "private_password" not in response.text
