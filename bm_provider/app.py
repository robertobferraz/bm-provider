from __future__ import annotations

import logging
import os

from aiohttp import web

from .spotapi_adapter import SpotAPIPlaylistAdapter

LOGGER = logging.getLogger("bm_provider")


def _truthy(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().casefold() in {"1", "true", "yes", "on"}


async def handle_resolve(request: web.Request) -> web.Response:
    expected_token = request.app["auth_token"]
    if expected_token:
        auth_header = request.headers.get("Authorization", "").strip()
        if auth_header != f"Bearer {expected_token}":
            return web.json_response({"error": "unauthorized"}, status=401)

    spotify_url = request.query.get("url", "").strip()
    kind = request.query.get("kind", "").strip().casefold() or None
    raw_limit = request.query.get("limit", "").strip()

    if not spotify_url:
        return web.json_response({"error": "missing url"}, status=400)

    limit: int | None = None
    if raw_limit:
        try:
            limit = max(1, int(raw_limit))
        except ValueError:
            return web.json_response({"error": "invalid limit"}, status=400)

    adapter: SpotAPIPlaylistAdapter = request.app["adapter"]
    try:
        payload = await adapter.resolve(url=spotify_url, kind=kind, limit=limit)
    except Exception as exc:
        LOGGER.exception("provider resolve failed kind=%s url=%s", kind, spotify_url)
        return web.json_response({"error": str(exc)}, status=502)
    return web.json_response(payload)


def build_app() -> web.Application:
    logging.basicConfig(
        level=getattr(logging, os.getenv("BM_PROVIDER_LOG_LEVEL", "INFO").strip().upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    adapter = SpotAPIPlaylistAdapter(
        language=os.getenv("BM_PROVIDER_LANGUAGE", "en").strip() or "en",
        strict_public_only=_truthy("BM_PROVIDER_PUBLIC_ONLY", "true"),
    )
    app = web.Application()
    app["adapter"] = adapter
    app["auth_token"] = os.getenv("BM_PROVIDER_AUTH_TOKEN", "").strip()
    app.router.add_get("/health", lambda _request: web.json_response({"ok": True}))
    app.router.add_get("/resolve", handle_resolve)
    return app


def main() -> None:
    app = build_app()
    host = os.getenv("BM_PROVIDER_HOST", "0.0.0.0").strip() or "0.0.0.0"
    port = int(os.getenv("BM_PROVIDER_PORT", "8081").strip() or "8081")
    web.run_app(app, host=host, port=port)


if __name__ == "__main__":
    main()
