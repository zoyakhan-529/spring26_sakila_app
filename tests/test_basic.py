from app import app
from config import Config


def test_app_exists():
    assert app is not None


def test_app_name():
    assert app.name == "app"


def test_config_defaults_exist():
    assert Config.MYSQL_HOST is not None
    assert Config.MYSQL_USER is not None
    assert Config.MYSQL_DB is not None


def test_dashboard_route_handles_database_error(monkeypatch):
    import app as app_module

    def fake_render_template(template_name, **context):
        return "dashboard fallback rendered"

    def fake_get_db_connection():
        raise Exception("database unavailable")

    monkeypatch.setattr(app_module, "render_template", fake_render_template)
    monkeypatch.setattr(app_module, "get_db_connection", fake_get_db_connection)

    client = app.test_client()
    response = client.get("/")

    assert response.status_code == 200
    assert b"dashboard fallback rendered" in response.data
