from __future__ import annotations

import asyncio
import re
from typing import Any

try:
    from spotapi import PublicPlaylist
    _SPOTAPI_IMPORT_ERROR: Exception | None = None
except Exception as exc:
    PublicPlaylist = None  # type: ignore[assignment]
    _SPOTAPI_IMPORT_ERROR = exc


class SpotAPIPlaylistAdapter:
    def __init__(self, *, language: str = "en", strict_public_only: bool = True) -> None:
        self.language = language
        self.strict_public_only = strict_public_only

    async def resolve(self, *, url: str, kind: str | None, limit: int | None) -> dict[str, Any]:
        normalized_kind = kind or self._kind_from_url(url)
        if normalized_kind not in {"playlist"}:
            raise RuntimeError(f"unsupported kind: {normalized_kind or 'unknown'}")
        if PublicPlaylist is None:
            detail = f": {_SPOTAPI_IMPORT_ERROR}" if _SPOTAPI_IMPORT_ERROR is not None else ""
            raise RuntimeError(f"spotapi unavailable in provider environment{detail}")
        return await asyncio.to_thread(self._resolve_playlist_sync, url, limit)

    def _resolve_playlist_sync(self, url: str, limit: int | None) -> dict[str, Any]:
        playlist = PublicPlaylist(url)  # type: ignore[misc]
        items: list[dict[str, Any]] = []
        invalid = 0
        total = 0
        for page in playlist.paginate_playlist():
            page_total = self._extract_total(page)
            if page_total > 0:
                total = max(total, page_total)
            for entry in self._iter_track_like_entries(page):
                track = self._normalize_track(entry, fallback_url=url)
                if track is None:
                    invalid += 1
                    continue
                items.append(track)
                if limit is not None and len(items) >= limit:
                    break
            if limit is not None and len(items) >= limit:
                break
        if not items:
            raise RuntimeError("spotapi returned no playable items")
        if total <= 0:
            total = len(items) + invalid
        return {"items": items, "total": total, "invalid_items": invalid}

    @staticmethod
    def _kind_from_url(url: str) -> str | None:
        match = re.search(r"open\.spotify\.com/(playlist|album|track)/", url)
        return match.group(1) if match else None

    @staticmethod
    def _extract_total(payload: Any) -> int:
        if isinstance(payload, dict):
            for key in ("totalCount", "total", "total_items"):
                value = payload.get(key)
                if isinstance(value, int):
                    return value
            for value in payload.values():
                total = SpotAPIPlaylistAdapter._extract_total(value)
                if total > 0:
                    return total
        elif isinstance(payload, list):
            for item in payload:
                total = SpotAPIPlaylistAdapter._extract_total(item)
                if total > 0:
                    return total
        return 0

    @staticmethod
    def _iter_track_like_entries(payload: Any) -> list[dict[str, Any]]:
        matches: list[dict[str, Any]] = []

        def visit(node: Any) -> None:
            if isinstance(node, dict):
                uri = str(node.get("uri") or "").strip()
                name = str(node.get("name") or node.get("title") or "").strip()
                if uri.startswith("spotify:track:") and name:
                    matches.append(node)
                    return
                data = node.get("data")
                if isinstance(data, dict):
                    data_uri = str(data.get("uri") or "").strip()
                    data_name = str(data.get("name") or data.get("title") or "").strip()
                    if data_uri.startswith("spotify:track:") and data_name:
                        matches.append(data)
                        return
                for value in node.values():
                    visit(value)
            elif isinstance(node, list):
                for item in node:
                    visit(item)

        visit(payload)
        return matches

    @staticmethod
    def _normalize_track(payload: dict[str, Any], *, fallback_url: str) -> dict[str, Any] | None:
        title = str(payload.get("name") or payload.get("title") or "").strip()
        if not title:
            return None
        uri = str(payload.get("uri") or "").strip()
        spotify_id = uri.split(":")[-1].strip() if uri.startswith("spotify:track:") else str(payload.get("id") or "").strip()
        spotify_url = (
            str(((payload.get("sharingInfo") or {}) if isinstance(payload.get("sharingInfo"), dict) else {}).get("shareUrl") or "").strip()
            or (f"https://open.spotify.com/track/{spotify_id}" if spotify_id else fallback_url)
        )
        artist_names = SpotAPIPlaylistAdapter._extract_artists(payload)
        duration_ms = SpotAPIPlaylistAdapter._extract_duration_ms(payload)
        isrc = SpotAPIPlaylistAdapter._extract_isrc(payload)
        return {
            "title": title,
            "artist": ", ".join(artist_names[:3]),
            "artists": artist_names,
            "duration_ms": duration_ms,
            "isrc": isrc,
            "spotify_url": spotify_url,
        }

    @staticmethod
    def _extract_artists(payload: dict[str, Any]) -> list[str]:
        names: list[str] = []
        candidates = payload.get("artists")
        if isinstance(candidates, list):
            for item in candidates:
                if isinstance(item, dict):
                    name = str(item.get("name") or "").strip()
                    if name:
                        names.append(name)
                elif isinstance(item, str) and item.strip():
                    names.append(item.strip())
        if not names:
            nested = ((payload.get("artists") or {}) if isinstance(payload.get("artists"), dict) else {}).get("items")
            if isinstance(nested, list):
                for item in nested:
                    profile = ((item.get("profile") or {}) if isinstance(item, dict) else {})
                    name = str(profile.get("name") or "").strip()
                    if name:
                        names.append(name)
        return names

    @staticmethod
    def _extract_duration_ms(payload: dict[str, Any]) -> int | None:
        def coerce_int(value: Any) -> int | None:
            if isinstance(value, bool):
                return None
            if isinstance(value, int):
                return value if value > 0 else None
            if isinstance(value, str):
                raw = value.strip()
                if raw.isdigit():
                    parsed = int(raw)
                    return parsed if parsed > 0 else None
            return None

        direct = coerce_int(payload.get("duration_ms"))
        if direct is not None:
            return direct

        duration = payload.get("duration")
        if isinstance(duration, dict):
            for key in ("totalMilliseconds", "milliseconds", "total_ms", "ms"):
                value = coerce_int(duration.get(key))
                if value is not None:
                    return value

        queue = [payload]
        seen: set[int] = set()
        preferred_keys = {
            "duration_ms",
            "durationMs",
            "totalMilliseconds",
            "milliseconds",
            "total_ms",
            "ms",
        }
        while queue:
            node = queue.pop(0)
            marker = id(node)
            if marker in seen:
                continue
            seen.add(marker)
            if isinstance(node, dict):
                for key, value in node.items():
                    if key in preferred_keys:
                        parsed = coerce_int(value)
                        if parsed is not None:
                            return parsed
                    if isinstance(value, (dict, list)):
                        queue.append(value)
            elif isinstance(node, list):
                for item in node:
                    if isinstance(item, (dict, list)):
                        queue.append(item)
        return None

    @staticmethod
    def _extract_isrc(payload: dict[str, Any]) -> str | None:
        direct = str(((payload.get("external_ids") or {}) if isinstance(payload.get("external_ids"), dict) else {}).get("isrc") or "").strip()
        if direct:
            return direct
        code = str(((payload.get("externalIds") or {}) if isinstance(payload.get("externalIds"), dict) else {}).get("isrc") or "").strip()
        return code or None
