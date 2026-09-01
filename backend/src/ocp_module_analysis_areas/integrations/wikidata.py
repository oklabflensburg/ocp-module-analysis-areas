"""Wikidata API adapter using only public Host HTTP and cache ports."""

import asyncio
import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any

from app.platform.modules.sdk import CachePort, HttpClientFactoryPort

from ..domain.wikidata import WikidataEntity

QID_RE = re.compile(r"^Q[1-9][0-9]*$")


class WikidataProviderError(RuntimeError):
    pass


def wikipedia_title(value: str | None) -> str | None:
    if not value:
        return None
    if value.startswith("de:"):
        return value[3:].strip() or None
    prefix = "https://de.wikipedia.org/wiki/"
    if value.startswith(prefix):
        return value[len(prefix) :].strip() or None
    return None


class WikidataClient:
    def __init__(
        self,
        http: HttpClientFactoryPort,
        cache: CachePort,
        *,
        api_url: str,
        cache_ttl_seconds: int,
        negative_cache_ttl_seconds: int,
        search_limit: int,
        sleep=asyncio.sleep,
    ) -> None:
        self._http = http
        self._cache = cache
        self._api_url = api_url
        self._cache_ttl = cache_ttl_seconds
        self._negative_cache_ttl = negative_cache_ttl_seconds
        self._search_limit = search_limit
        self._sleep = sleep

    async def _request(self, params: Mapping[str, str]) -> dict[str, Any]:
        encoded = json.dumps(params, sort_keys=True, separators=(",", ":")).encode()
        key = f"wikidata:v1:{hashlib.sha256(encoded).hexdigest()}"
        cached = await self._cache.get(key)
        if cached is not None:
            value = json.loads(cached)
            if not isinstance(value, dict):
                raise WikidataProviderError("Cached Wikidata response is not an object")
            return value

        last_error: Exception | None = None
        for attempt in range(3):
            try:
                async with self._http.create(
                    service_name="wikidata", base_url=self._api_url
                ) as client:
                    try:
                        response = await client.request(
                            "GET",
                            self._api_url,
                            headers={"Accept": "application/json"},
                            params={**params, "format": "json", "formatversion": "2"},
                        )
                    except Exception as exc:  # public HTTP port intentionally hides transport types
                        last_error = exc
                        if attempt < 2:
                            await self._sleep(float(attempt + 1))
                            continue
                        raise
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt < 2:
                        retry_after = response.headers.get("Retry-After", str(attempt + 1))
                        try:
                            delay = min(float(retry_after), 5.0)
                        except ValueError:
                            delay = float(attempt + 1)
                        await self._sleep(max(delay, 0.0))
                        continue
                    raise WikidataProviderError(
                        f"Wikidata returned HTTP {response.status_code}"
                    )
                if response.status_code < 200 or response.status_code >= 300:
                    raise WikidataProviderError(
                        f"Wikidata returned HTTP {response.status_code}"
                    )
                payload = response.json()
                if not isinstance(payload, dict):
                    raise WikidataProviderError("Wikidata response is not an object")
                ttl = self._cache_ttl
                if _is_negative(payload):
                    ttl = self._negative_cache_ttl
                await self._cache.set(
                    key,
                    json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode(),
                    ttl_seconds=ttl,
                )
                return payload
            except (TimeoutError, OSError) as exc:
                last_error = exc
                if attempt < 2:
                    await self._sleep(float(attempt + 1))
                    continue
        if last_error is not None:
            raise last_error
        raise WikidataProviderError("Wikidata request failed")

    async def entity(self, qid: str) -> WikidataEntity | None:
        if not QID_RE.fullmatch(qid):
            return None
        payload = await self._request(
            {
                "action": "wbgetentities",
                "ids": qid,
                "props": "labels|descriptions|aliases|claims|sitelinks/urls",
                "languages": "de|en",
                "sitefilter": "dewiki",
            }
        )
        entities = payload.get("entities")
        raw = entities.get(qid) if isinstance(entities, dict) else None
        return self._parse_entity(raw) if isinstance(raw, dict) and "missing" not in raw else None

    async def entity_from_dewiki(self, title: str) -> WikidataEntity | None:
        payload = await self._request(
            {
                "action": "wbgetentities",
                "sites": "dewiki",
                "titles": title,
                "props": "labels|descriptions|aliases|claims|sitelinks/urls",
                "languages": "de|en",
                "sitefilter": "dewiki",
            }
        )
        entities = payload.get("entities")
        values = entities.values() if isinstance(entities, dict) else ()
        raw = next(
            (
                value
                for value in values
                if isinstance(value, dict) and "missing" not in value
            ),
            None,
        )
        return self._parse_entity(raw) if raw is not None else None

    async def search(self, query: str) -> list[WikidataEntity]:
        payload = await self._request(
            {
                "action": "wbsearchentities",
                "search": query,
                "language": "de",
                "uselang": "de",
                "type": "item",
                "limit": str(self._search_limit),
            }
        )
        search = payload.get("search")
        items = search if isinstance(search, list) else []
        ids = [
            item.get("id")
            for item in items
            if isinstance(item, dict) and QID_RE.fullmatch(str(item.get("id", "")))
        ]
        result: list[WikidataEntity] = []
        for qid in ids:
            entity = await self.entity(str(qid))
            if entity is not None:
                result.append(entity)
        return result

    @staticmethod
    def _parse_entity(raw: Mapping[str, Any]) -> WikidataEntity:
        def localized(field: str) -> str | None:
            values = raw.get(field)
            if not isinstance(values, dict):
                return None
            selected = values.get("de") or values.get("en") or {}
            return selected.get("value") if isinstance(selected, dict) else None

        raw_aliases = raw.get("aliases")
        aliases_by_language = raw_aliases if isinstance(raw_aliases, dict) else {}
        aliases = aliases_by_language.get("de") or aliases_by_language.get("en") or []
        coordinate = _claim_value(raw, "P625")
        coordinate = coordinate if isinstance(coordinate, dict) else {}
        parent_ids = tuple(
            value["id"]
            for value in _claim_values(raw, "P131")
            if isinstance(value, dict) and QID_RE.fullmatch(str(value.get("id", "")))
        )
        raw_sitelinks = raw.get("sitelinks")
        sitelinks = raw_sitelinks if isinstance(raw_sitelinks, dict) else {}
        dewiki = sitelinks.get("dewiki") or {}
        return WikidataEntity(
            id=str(raw["id"]),
            label=localized("labels"),
            description=localized("descriptions"),
            wikipedia_title=dewiki.get("title") if isinstance(dewiki, dict) else None,
            aliases=tuple(
                str(item["value"])
                for item in aliases
                if isinstance(item, dict) and item.get("value")
            ),
            latitude=_float_or_none(coordinate.get("latitude")),
            longitude=_float_or_none(coordinate.get("longitude")),
            parent_ids=parent_ids,
        )


def _claim_values(raw: Mapping[str, Any], prop: str) -> list[Any]:
    claims = raw.get("claims")
    values: list[Any] = []
    for claim in claims.get(prop, []) if isinstance(claims, dict) else []:
        if not isinstance(claim, dict):
            continue
        snak = claim.get("mainsnak") or {}
        data = snak.get("datavalue") or {} if isinstance(snak, dict) else {}
        if isinstance(snak, dict) and snak.get("snaktype") == "value" and isinstance(data, dict):
            values.append(data.get("value"))
    return values


def _claim_value(raw: Mapping[str, Any], prop: str) -> Any | None:
    values = _claim_values(raw, prop)
    return values[0] if values else None


def _float_or_none(value: object) -> float | None:
    return float(value) if isinstance(value, int | float) else None


def _is_negative(payload: Mapping[str, Any]) -> bool:
    search = payload.get("search")
    if isinstance(search, list):
        return not search
    entities = payload.get("entities")
    if isinstance(entities, dict):
        return not entities or all(
            isinstance(value, dict) and "missing" in value
            for value in entities.values()
        )
    return True
