import argparse
import asyncio
import sys
import uuid
from collections.abc import Sequence

import structlog

from gateforge.core.database import async_session_factory
from gateforge.core.redis_client import get_resilient_redis
from gateforge.services.api_key import APIKeyService
from gateforge.services.auth_cache import AuthCacheService

logger = structlog.get_logger(__name__)


async def handle_create_key(args: argparse.Namespace) -> None:
    """CLI handler to generate and persist a new cryptographic API key."""
    try:
        user_uuid = uuid.UUID(args.user_id)
    except ValueError:
        print(f"Error: Invalid UUID format for user-id: {args.user_id}", file=sys.stderr)
        sys.exit(1)

    scopes = args.scopes.split(",") if args.scopes else []
    allowed_ips = args.allowed_ips.split(",") if args.allowed_ips else []

    async with async_session_factory() as session:
        api_key, raw_key = await APIKeyService.create_key(
            session=session,
            user_id=user_uuid,
            name=args.name,
            scopes=scopes,
            allowed_ips=allowed_ips,
            custom_rate_limit_rpm=args.rate_limit,
        )

    print("\n--- GateForge API Key Created Successfully ---")
    print(f"Key ID:       {api_key.id}")
    print(f"Key Name:     {api_key.name}")
    print(f"Owner:        {api_key.user_id}")
    print(f"Masked:       {api_key.masked_display}")
    print(f"Rate Limit:   {api_key.custom_rate_limit_rpm or 'default (60 RPM)'}")
    print(f"Allowed IPs:  {api_key.allowed_ips or 'Any'}")
    print(f"\nRAW SECRET TOKEN (Shown ONCE - store securely):\n{raw_key}\n")


async def handle_revoke_key(args: argparse.Namespace) -> None:
    """CLI handler to revoke an existing API key and purge edge cache."""
    try:
        key_uuid = uuid.UUID(args.key_id)
    except ValueError:
        print(f"Error: Invalid UUID format for key-id: {args.key_id}", file=sys.stderr)
        sys.exit(1)

    cache_service = AuthCacheService()
    async with async_session_factory() as session:
        revoked = await APIKeyService.revoke_key(
            session=session,
            key_id=key_uuid,
            cache_service=cache_service,
        )

    if revoked is None:
        print(f"Error: API Key with ID {key_uuid} not found.", file=sys.stderr)
        sys.exit(1)

    print(f"Successfully revoked API key {key_uuid} ({revoked.name}). Cache purged.")


async def handle_purge_cache(args: argparse.Namespace) -> None:
    """CLI handler to invalidate cached keys in Redis."""
    cache_service = AuthCacheService()
    if args.raw_key:
        purged = await cache_service.invalidate_key(args.raw_key)
        print(f"Purge result for raw key: {'Success' if purged else 'Key not found in cache'}")
    elif args.key_hash:
        purged = await cache_service.invalidate_key_by_hash(args.key_hash)
        print(f"Purge result for hash {args.key_hash}: {'Success' if purged else 'Key not found in cache'}")
    else:
        print("Error: Specify either --raw-key or --key-hash to purge.", file=sys.stderr)
        sys.exit(1)


async def handle_status() -> None:
    """CLI handler to inspect infrastructure health connectivity."""
    redis_client = get_resilient_redis()
    redis_alive = await redis_client.ping()

    db_alive = False
    try:
        async with async_session_factory() as session:
            from sqlalchemy import text
            await session.execute(text("SELECT 1"))
            db_alive = True
    except Exception as exc:
        logger.warning("cli_db_ping_failed", error=str(exc))

    print("\n--- GateForge Infrastructure Status ---")
    print(f"PostgreSQL Database: {'CONNECTED' if db_alive else 'OFFLINE / UNREACHABLE'}")
    print(f"Redis Edge Cache:    {'CONNECTED' if redis_alive else 'OFFLINE / UNREACHABLE'}")
    print()


def build_parser() -> argparse.ArgumentParser:
    """Construct CLI command-line argument parser."""
    parser = argparse.ArgumentParser(
        prog="gateforge-cli",
        description="GateForge Administrative Operations and Key Management Utility",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # create-key
    create_p = subparsers.add_parser("create-key", help="Generate a new cryptographic API key")
    create_p.add_argument("--name", required=True, help="Human-readable name for key")
    create_p.add_argument("--user-id", required=True, help="Owner User UUID")
    create_p.add_argument("--scopes", default="", help="Comma-separated scopes (e.g. read:data,write:data)")
    create_p.add_argument("--allowed-ips", default="", help="Comma-separated CIDRs or IPs (e.g. 192.168.1.0/24)")
    create_p.add_argument("--rate-limit", type=int, default=None, help="Custom requests-per-minute quota")

    # revoke-key
    revoke_p = subparsers.add_parser("revoke-key", help="Revoke an existing API key and purge cache")
    revoke_p.add_argument("--key-id", required=True, help="UUID of key to revoke")

    # purge-cache
    purge_p = subparsers.add_parser("purge-cache", help="Invalidate key from edge Redis cache")
    purge_p.add_argument("--raw-key", help="Plaintext API key token")
    purge_p.add_argument("--key-hash", help="SHA-256 key hash")

    # status
    subparsers.add_parser("status", help="Inspect Redis and Database health connectivity")

    return parser


def main(argv: Sequence[str] | None = None) -> None:
    """CLI execution entrypoint."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "create-key":
        asyncio.run(handle_create_key(args))
    elif args.command == "revoke-key":
        asyncio.run(handle_revoke_key(args))
    elif args.command == "purge-cache":
        asyncio.run(handle_purge_cache(args))
    elif args.command == "status":
        asyncio.run(handle_status())


if __name__ == "__main__":
    main()
