from gateforge.core.config import Settings
from gateforge.main import create_app


def test_create_app_development_mode() -> None:
    """Verify app creation with development settings exposes docs."""
    settings = Settings(ENVIRONMENT="development", DEBUG=True)
    app = create_app(settings)

    assert app.title == settings.PROJECT_NAME
    assert app.debug is True
    assert app.docs_url == "/docs"
    assert app.redoc_url == "/redoc"


def test_create_app_production_mode() -> None:
    """Verify app creation in production disables public OpenAPI documentation."""
    settings = Settings(ENVIRONMENT="production", DEBUG=False)
    app = create_app(settings)

    assert app.docs_url is None
    assert app.redoc_url is None
