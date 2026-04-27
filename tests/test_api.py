from app import app


def test_actor_api_returns_json_error_when_db_fails(monkeypatch):
    import app as app_module

    def fake_get_db_connection():
        raise Exception("database unavailable")

    monkeypatch.setattr(app_module, "get_db_connection", fake_get_db_connection)

    client = app.test_client()
    response = client.get("/api/actor/1")

    assert response.status_code == 500
    data = response.get_json()
    assert data is not None
    assert "error" in data


def test_film_api_returns_json_error_when_db_fails(monkeypatch):
    import app as app_module

    def fake_get_db_connection():
        raise Exception("database unavailable")

    monkeypatch.setattr(app_module, "get_db_connection", fake_get_db_connection)

    client = app.test_client()
    response = client.get("/api/film/1")

    assert response.status_code == 500
    data = response.get_json()
    assert data is not None
    assert "error" in data
