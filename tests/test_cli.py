
from gateforge.cli import build_parser


def test_cli_build_parser_create_key() -> None:
    """Verify CLI parser handles create-key flags correctly."""
    parser = build_parser()
    args = parser.parse_args([
        "create-key",
        "--name", "Test Service",
        "--user-id", "12345678-1234-5678-1234-567812345678",
        "--scopes", "read:metrics,write:orders",
        "--allowed-ips", "192.168.1.0/24",
        "--rate-limit", "120",
    ])
    assert args.command == "create-key"
    assert args.name == "Test Service"
    assert args.user_id == "12345678-1234-5678-1234-567812345678"
    assert args.scopes == "read:metrics,write:orders"
    assert args.allowed_ips == "192.168.1.0/24"
    assert args.rate_limit == 120


def test_cli_build_parser_revoke_key() -> None:
    """Verify CLI parser handles revoke-key flags."""
    parser = build_parser()
    args = parser.parse_args([
        "revoke-key",
        "--key-id", "87654321-4321-8765-4321-876543218765",
    ])
    assert args.command == "revoke-key"
    assert args.key_id == "87654321-4321-8765-4321-876543218765"


def test_cli_build_parser_status() -> None:
    """Verify CLI parser handles status command."""
    parser = build_parser()
    args = parser.parse_args(["status"])
    assert args.command == "status"
