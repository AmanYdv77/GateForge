import importlib.util
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

from gateforge.core.config import get_settings


def test_alembic_migration_revisions_chain() -> None:
    """Verify that Alembic migration revision history forms an unbroken topological order."""
    settings = get_settings()
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

    script = ScriptDirectory.from_config(config)
    revisions = list(script.walk_revisions())

    revision_ids = [rev.revision for rev in revisions]
    assert "003_api_keys_allowed_ips" in revision_ids
    assert "002_telemetry_and_rollups" in revision_ids
    assert "001_initial_schema" in revision_ids
    assert len(revisions) == 3
    # Verify topological order from head to base
    assert revision_ids[0] == "003_api_keys_allowed_ips"
    assert revision_ids[1] == "002_telemetry_and_rollups"
    assert revision_ids[2] == "001_initial_schema"


def test_migration_002_metadata_and_callables() -> None:
    """Verify migration 002 attributes, down_revision linkage, and upgrade/downgrade callables."""
    config = Config("alembic.ini")
    script = ScriptDirectory.from_config(config)

    rev_002 = script.get_revision("002_telemetry_and_rollups")
    assert rev_002 is not None
    assert rev_002.down_revision == "001_initial_schema"

    migration_path = Path("alembic/versions/002_telemetry_and_rollups.py")
    assert migration_path.exists()

    spec = importlib.util.spec_from_file_location("migration_002", migration_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert callable(getattr(module, "upgrade", None))
    assert callable(getattr(module, "downgrade", None))
    assert module.revision == "002_telemetry_and_rollups"
    assert module.down_revision == "001_initial_schema"


def test_migration_003_metadata_and_callables() -> None:
    """Verify migration 003 attributes, down_revision linkage, and upgrade/downgrade callables."""
    config = Config("alembic.ini")
    script = ScriptDirectory.from_config(config)

    rev_003 = script.get_revision("003_api_keys_allowed_ips")
    assert rev_003 is not None
    assert rev_003.down_revision == "002_telemetry_and_rollups"

    migration_path = Path("alembic/versions/003_api_keys_allowed_ips.py")
    assert migration_path.exists()

    spec = importlib.util.spec_from_file_location("migration_003", migration_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert callable(getattr(module, "upgrade", None))
    assert callable(getattr(module, "downgrade", None))
    assert module.revision == "003_api_keys_allowed_ips"
    assert module.down_revision == "002_telemetry_and_rollups"
