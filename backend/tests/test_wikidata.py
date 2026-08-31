from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime

import httpx
import pytest

from ocp_module_analysis_areas.application.wikidata import (
    WikidataEnrichmentService,
    WikidataNameMismatchError,
)
from ocp_module_analysis_areas.domain.wikidata import AreaSnapshot, Match, WikidataEntity
from ocp_module_analysis_areas.integrations import wikidata as wikidata_integration
from ocp_module_analysis_areas.integrations.wikidata import (
    WikidataClient,
    WikidataProviderError,
    wikipedia_title,
)


def area(**changes: object) -> AreaSnapshot:
    values = {
        "id": 1,
        "name": "Flensburg",
        "area_type": "MUNICIPALITY",
        "latitude": 54.78,
        "longitude": 9.43,
        "municipality_name": "Flensburg",
    }
    values.update(changes)
    return AreaSnapshot(**values)


class MemoryCache:
    def __init__(self) -> None:
        self.values: dict[str, bytes] = {}
        self.ttls: list[int] = []
        self.clears = 0

    async def get(self, key: str) -> bytes | None:
        return self.values.get(key)

    async def set(self, key: str, value: bytes, *, ttl_seconds: int) -> bool:
        self.values[key] = value
        self.ttls.append(ttl_seconds)
        return True

    async def clear(self) -> int:
        self.clears += 1
        count = len(self.values)
        self.values.clear()
        return count


class Response:
    def __init__(self, status_code: int, payload: object, headers=None) -> None:
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}
        self.content = b""

    def json(self) -> object:
        return self._payload


class HttpClient:
    def __init__(self, responses: list[object]) -> None:
        self.responses = responses
        self.calls = 0

    async def request(self, *_args, **_kwargs):
        value = self.responses[self.calls]
        self.calls += 1
        if isinstance(value, BaseException):
            raise value
        return value


class HttpFactory:
    def __init__(self, client: HttpClient) -> None:
        self.client = client

    @asynccontextmanager
    async def create(self, **_kwargs):
        yield self.client


def entity_payload(qid: str = "Q482") -> dict:
    return {
        "entities": {
            qid: {
                "id": qid,
                "labels": {"de": {"value": "Flensburg"}},
                "descriptions": {
                    "de": {"value": "kreisfreie Stadt in Schleswig-Holstein"}
                },
                "aliases": {"de": [{"value": "Flensborg"}]},
                "claims": {
                    "P625": [
                        {
                            "mainsnak": {
                                "snaktype": "value",
                                "datavalue": {
                                    "value": {"latitude": 54.78, "longitude": 9.43}
                                },
                            }
                        }
                    ]
                },
                "sitelinks": {"dewiki": {"title": "Flensburg"}},
            }
        }
    }


def client(responses: list[object], cache: MemoryCache | None = None, sleep=None):
    http = HttpClient(responses)
    kwargs = {"sleep": sleep} if sleep is not None else {}
    return (
        WikidataClient(
            HttpFactory(http),
            cache or MemoryCache(),
            api_url="https://www.wikidata.org/w/api.php",
            cache_ttl_seconds=700,
            negative_cache_ttl_seconds=80,
            search_limit=8,
            **kwargs,
        ),
        http,
    )


@pytest.mark.asyncio
async def test_provider_parses_entity_and_caches_success() -> None:
    cache = MemoryCache()
    provider, http = client([Response(200, entity_payload())], cache)
    first = await provider.entity("Q482")
    second = await provider.entity("Q482")
    assert first == second
    assert first and first.wikipedia_title == "Flensburg"
    assert first.aliases == ("Flensborg",)
    assert http.calls == 1
    assert cache.ttls == [700]


@pytest.mark.asyncio
async def test_provider_retries_timeout_and_uses_negative_ttl() -> None:
    sleeps: list[float] = []

    async def sleep(delay: float) -> None:
        sleeps.append(delay)

    cache = MemoryCache()
    provider, http = client(
        [TimeoutError(), Response(200, {"entities": {"Q9": {"id": "Q9", "missing": ""}}})],
        cache,
        sleep,
    )
    assert await provider.entity("Q9") is None
    assert http.calls == 2
    assert sleeps == [1.0]
    assert cache.ttls == [80]


@pytest.mark.asyncio
async def test_httpx_fallback_applies_policy_retries_and_closes_clients(monkeypatch) -> None:
    clients = []
    requests = []

    class FallbackClient:
        def __init__(self, *, timeout: float) -> None:
            self.timeout = timeout
            self.entered = False
            self.closed = False
            clients.append(self)

        async def __aenter__(self):
            self.entered = True
            return self

        async def __aexit__(self, *_args):
            self.closed = True

        async def request(self, method, url, **kwargs):
            requests.append((method, url, kwargs))
            if len(requests) == 1:
                raise httpx.ReadTimeout("temporary timeout")
            return Response(200, entity_payload())

    monkeypatch.setattr(wikidata_integration.httpx, "AsyncClient", FallbackClient)
    provider = WikidataClient(
        None,
        MemoryCache(),
        api_url="https://www.wikidata.org/w/api.php",
        cache_ttl_seconds=700,
        negative_cache_ttl_seconds=80,
        search_limit=8,
        timeout_seconds=4.5,
        user_agent="analysis-areas-test/1.0",
        sleep=lambda _delay: _completed(),
    )

    assert (await provider.entity("Q482")).id == "Q482"
    assert len(requests) == 2
    assert all(client.timeout == 4.5 for client in clients)
    assert all(client.entered and client.closed for client in clients)
    assert requests[1][2]["headers"]["User-Agent"] == "analysis-areas-test/1.0"


@pytest.mark.asyncio
async def test_provider_rejects_http_and_invalid_json_shapes() -> None:
    no_sleep = lambda _delay: _completed()
    provider, _ = client([Response(400, {})], sleep=no_sleep)
    with pytest.raises(WikidataProviderError, match="HTTP 400"):
        await provider.entity("Q1")
    provider, _ = client([Response(200, [])], sleep=no_sleep)
    with pytest.raises(WikidataProviderError, match="not an object"):
        await provider.entity("Q1")


async def _completed() -> None:
    return None


class MatchingClient:
    async def entity(self, qid: str):
        return WikidataEntity(qid, "Flensburg", "kreisfreie Stadt", "Flensburg")

    async def entity_from_dewiki(self, _title: str):
        return WikidataEntity("Q42", "Other", None, "Other")

    async def search(self, _query: str):
        return []


@pytest.mark.asyncio
async def test_explicit_osm_qid_wins_and_conflict_is_preserved() -> None:
    service = WikidataEnrichmentService(None, None, MatchingClient(), stale_days=90)
    match = await service.resolve_area(
        area(source_osm_wikidata="Q482", source_osm_wikipedia="de:Other")
    )
    assert match == Match(
        "CONFLICT",
        "OSM_WIKIDATA",
        1.0,
        WikidataEntity("Q482", "Flensburg", "kreisfreie Stadt", "Flensburg"),
    )


@pytest.mark.asyncio
async def test_invalid_explicit_qid_never_falls_back() -> None:
    class NoCalls:
        def __getattr__(self, _name):
            raise AssertionError("provider must not be called")

    service = WikidataEnrichmentService(None, None, NoCalls(), stale_days=90)
    assert await service.resolve_area(area(source_osm_wikidata="Q1;Q2")) == Match(
        "INVALID", "OSM_WIKIDATA"
    )


def test_contextual_validation_matches_historical_scoring() -> None:
    snapshot = area(
        name="Innenstadt",
        area_type="DISTRICT",
        parent_name="Flensburg",
        parent_wikidata_id="Q482",
    )
    valid = WikidataEntity(
        "Q1",
        "Innenstadt",
        "Stadtteil von Flensburg",
        None,
        latitude=54.781,
        longitude=9.431,
        parent_ids=("Q482",),
    )
    invalid = WikidataEntity(
        "Q2",
        "Innenstadt",
        "Stadtteil einer anderen Stadt",
        None,
        latitude=52.5,
        longitude=13.4,
    )
    assert WikidataEnrichmentService.validate_candidate(snapshot, valid) == 1.0
    assert WikidataEnrichmentService.validate_candidate(snapshot, invalid) == 0.0


def test_only_german_wikipedia_values_are_normalized() -> None:
    assert wikipedia_title("de:Flensburg") == "Flensburg"
    assert wikipedia_title("https://de.wikipedia.org/wiki/Flensburg") == "Flensburg"
    assert wikipedia_title("en:Flensburg") is None


class Rows:
    def __init__(self, values: list[object]) -> None:
        self.values = values

    def mappings(self):
        return self

    def all(self):
        return self.values

    def first(self):
        return self.values[0] if self.values else None


class Session:
    def __init__(self, rows: list[object]) -> None:
        self.rows = rows
        self.writes: list[dict] = []
        self.commits = 0

    async def execute(self, statement, parameters):
        if str(statement).lstrip().startswith("SELECT"):
            return Rows(self.rows)
        self.writes.append(parameters)
        return Rows([])

    async def commit(self):
        self.commits += 1


class Database:
    def __init__(self, sessions: list[Session]) -> None:
        self.sessions = sessions
        self.active = 0

    @asynccontextmanager
    async def session(self):
        session = self.sessions.pop(0)
        self.active += 1
        try:
            yield session
        finally:
            self.active -= 1


class StatefulDatabase:
    def __init__(self, row: dict[str, object]) -> None:
        self.row = row
        self.provider_calls = 0
        self.commits = 0

    @asynccontextmanager
    async def session(self):
        database = self

        class StatefulSession:
            async def execute(self, statement, parameters):
                if str(statement).lstrip().startswith("SELECT"):
                    fresh = (
                        database.row["wikidata_last_checked_at"] is not None
                        and database.row["wikidata_last_checked_at"]
                        >= parameters["stale_before"]
                        and database.row["wikidata_match_status"]
                        in {"VERIFIED", "AUTO_MATCHED"}
                    )
                    if fresh and not parameters["force"]:
                        return Rows([])
                    fields = (
                        "id",
                        "name",
                        "area_type",
                        "source_osm_wikidata",
                        "source_osm_wikipedia",
                        "parent_name",
                        "parent_wikidata_id",
                        "municipality_name",
                        "latitude",
                        "longitude",
                    )
                    return Rows([{field: database.row[field] for field in fields}])
                database.row["wikidata_match_status"] = parameters["status"]
                database.row["wikidata_last_checked_at"] = datetime.now(UTC)
                return Rows([])

            async def commit(self):
                database.commits += 1

        yield StatefulSession()


@pytest.mark.asyncio
async def test_sync_releases_read_session_before_network_and_reuses_existing_row() -> None:
    read = Session(
        [
            {
                "id": 17,
                "name": "Flensburg",
                "area_type": "MUNICIPALITY",
                "source_osm_wikidata": "Q482",
                "source_osm_wikipedia": None,
                "parent_name": None,
                "parent_wikidata_id": None,
                "municipality_name": "Flensburg",
                "latitude": 54.78,
                "longitude": 9.43,
            }
        ]
    )
    write = Session([])
    database = Database([read, write])

    class NetworkClient:
        async def entity(self, qid: str):
            assert database.active == 0
            return WikidataEntity(qid, "Flensburg", "kreisfreie Stadt", "Flensburg")

    cache = MemoryCache()
    service = WikidataEnrichmentService(database, cache, NetworkClient(), stale_days=90)
    report = await service.sync()
    assert report.checked == report.osm_wikidata == 1
    assert write.writes[0]["area_id"] == 17
    assert write.commits == 1
    assert cache.clears == 1


@pytest.mark.asyncio
async def test_provider_error_isolated() -> None:
    row = {
        "id": 17,
        "name": "Flensburg",
        "area_type": "MUNICIPALITY",
        "source_osm_wikidata": "Q482",
        "source_osm_wikipedia": None,
        "parent_name": None,
        "parent_wikidata_id": None,
        "municipality_name": "Flensburg",
        "latitude": 54.78,
        "longitude": 9.43,
    }
    database = Database([Session([row])])

    class FailedClient:
        async def entity(self, _qid: str):
            raise TimeoutError

    cache = MemoryCache()
    service = WikidataEnrichmentService(database, cache, FailedClient(), stale_days=90)
    first = await service.sync()
    assert first.errors == ("Flensburg: TimeoutError",)
    assert cache.clears == 0


@pytest.mark.asyncio
async def test_second_normal_run_skips_fresh_persisted_match() -> None:
    database = StatefulDatabase(
        {
            "id": 17,
            "name": "Flensburg",
            "area_type": "MUNICIPALITY",
            "source_osm_wikidata": "Q482",
            "source_osm_wikipedia": None,
            "parent_name": None,
            "parent_wikidata_id": None,
            "municipality_name": "Flensburg",
            "latitude": 54.78,
            "longitude": 9.43,
            "wikidata_match_status": None,
            "wikidata_last_checked_at": None,
        }
    )

    class NetworkClient:
        async def entity(self, qid: str):
            database.provider_calls += 1
            return WikidataEntity(qid, "Flensburg", "kreisfreie Stadt", "Flensburg")

    cache = MemoryCache()
    service = WikidataEnrichmentService(database, cache, NetworkClient(), stale_days=90)

    first = await service.sync()
    persisted_at = database.row["wikidata_last_checked_at"]
    second = await service.sync()

    assert first.checked == first.osm_wikidata == 1
    assert database.row["wikidata_match_status"] == "AUTO_MATCHED"
    assert isinstance(persisted_at, datetime)
    assert second.checked == 0
    assert database.provider_calls == 1
    assert database.commits == cache.clears == 1


@pytest.mark.asyncio
async def test_manual_assignment_validates_without_holding_a_database_session() -> None:
    read = Session([(23, "Flensburg")])
    write = Session([])
    database = Database([read, write])

    class NetworkClient:
        async def entity(self, qid: str):
            assert database.active == 0
            return WikidataEntity(qid, "Flensburg", "kreisfreie Stadt", "Flensburg")

    cache = MemoryCache()
    service = WikidataEnrichmentService(database, cache, NetworkClient(), stale_days=90)
    await service.set_manual_match("flensburg-3017382", "Q482")
    assert write.writes == [
        {
            "area_id": 23,
            "qid": "Q482",
            "title": "Flensburg",
            "label": "Flensburg",
            "description": "kreisfreie Stadt",
        }
    ]
    assert write.commits == cache.clears == 1


@pytest.mark.asyncio
async def test_manual_assignment_rejects_name_mismatch_unless_confirmed() -> None:
    database = Database([Session([(23, "Flensburg")])])

    class NetworkClient:
        async def entity(self, qid: str):
            return WikidataEntity(qid, "Berlin", None, "Berlin")

    service = WikidataEnrichmentService(database, MemoryCache(), NetworkClient(), stale_days=90)
    with pytest.raises(WikidataNameMismatchError):
        await service.set_manual_match("flensburg-3017382", "Q64")
