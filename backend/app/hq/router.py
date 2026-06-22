"""Read-only HQ control-plane endpoints under ``/api/v1/hq``.

Every endpoint is GET-only and gated by ``require_view`` — fleet state is internal
and must not leak to unauthenticated callers. Responses use the standard
:class:`Envelope`; ``meta`` carries ``generated_at`` and per-source ``sources``
health so the UI can flag stale/unhealthy/mock upstreams.
"""

from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, Depends

from backend.app.auth import require_view
from backend.app.config import Settings, get_settings
from backend.app.hq.adapters.base import ControlPlaneSource
from backend.app.hq.adapters.mock import MockAdapter
from backend.app.hq.adapters.sigmacontrol import SigmaControlAdapter
from backend.app.hq.adapters.sigmalink import SigmaLinkAdapter
from backend.app.hq.models import (
    Blocker,
    Heartbeat,
    Overview,
    Project,
    Session,
    Swarm,
    Task,
    Worker,
)
from backend.app.hq.service import HQService
from backend.app.schemas import Envelope

router = APIRouter(prefix="/api/v1/hq", tags=["HQ"])

UNAUTHORIZED = {401: {"description": "Missing or invalid admin bearer token."}}


def build_sources(settings: Settings) -> list[ControlPlaneSource]:
    sources: list[ControlPlaneSource] = [
        SigmaControlAdapter(settings.hq_sigmacontrol_state),
        SigmaLinkAdapter(settings.hq_sigmalink_state),
    ]
    if settings.hq_use_mock:
        sources.append(MockAdapter())
    return sources


@lru_cache
def _service_singleton() -> HQService:
    settings = get_settings()
    return HQService(
        build_sources(settings),
        ttl_seconds=settings.hq_cache_ttl_seconds,
        stale_seconds=settings.hq_heartbeat_stale_seconds,
    )


def get_hq_service() -> HQService:
    """Process-wide singleton so the TTL cache survives across requests.

    Overridable in tests via ``app.dependency_overrides[get_hq_service]``.
    """
    return _service_singleton()


def _meta(snap: dict) -> dict:
    return {"generated_at": snap["generated_at"], "sources": snap["sources"]}


def ok(data: object, meta: dict | None = None) -> Envelope:
    return Envelope(data=data, meta=meta or {}, error=None)


@router.get(
    "/overview",
    response_model=Envelope[Overview],
    summary="Fleet overview",
    responses={**UNAUTHORIZED},
)
def hq_overview(
    svc: HQService = Depends(get_hq_service),
    _: object = Depends(require_view),
) -> Envelope:
    """Aggregated counts + per-source health for the whole fleet."""
    snap = svc.get_snapshot()
    return ok(svc.get_overview(), _meta(snap))


@router.get(
    "/workers",
    response_model=Envelope[list[Worker]],
    summary="Workers / agents",
    responses={**UNAUTHORIZED},
)
def hq_workers(
    svc: HQService = Depends(get_hq_service),
    _: object = Depends(require_view),
) -> Envelope:
    snap = svc.get_snapshot()
    return ok(snap["workers"], _meta(snap))


@router.get(
    "/sessions",
    response_model=Envelope[list[Session]],
    summary="Active sessions",
    responses={**UNAUTHORIZED},
)
def hq_sessions(
    svc: HQService = Depends(get_hq_service),
    _: object = Depends(require_view),
) -> Envelope:
    snap = svc.get_snapshot()
    return ok(snap["sessions"], _meta(snap))


@router.get(
    "/swarms",
    response_model=Envelope[list[Swarm]],
    summary="Swarms",
    responses={**UNAUTHORIZED},
)
def hq_swarms(
    svc: HQService = Depends(get_hq_service),
    _: object = Depends(require_view),
) -> Envelope:
    snap = svc.get_snapshot()
    return ok(snap["swarms"], _meta(snap))


@router.get(
    "/projects",
    response_model=Envelope[list[Project]],
    summary="Projects",
    responses={**UNAUTHORIZED},
)
def hq_projects(
    svc: HQService = Depends(get_hq_service),
    _: object = Depends(require_view),
) -> Envelope:
    snap = svc.get_snapshot()
    return ok(snap["projects"], _meta(snap))


@router.get(
    "/tasks",
    response_model=Envelope[list[Task]],
    summary="Tasks",
    responses={**UNAUTHORIZED},
)
def hq_tasks(
    svc: HQService = Depends(get_hq_service),
    _: object = Depends(require_view),
) -> Envelope:
    snap = svc.get_snapshot()
    return ok(snap["tasks"], _meta(snap))


@router.get(
    "/blockers",
    response_model=Envelope[list[Blocker]],
    summary="Blockers",
    responses={**UNAUTHORIZED},
)
def hq_blockers(
    svc: HQService = Depends(get_hq_service),
    _: object = Depends(require_view),
) -> Envelope:
    snap = svc.get_snapshot()
    return ok(snap["blockers"], _meta(snap))


@router.get(
    "/heartbeats",
    response_model=Envelope[list[Heartbeat]],
    summary="Heartbeats / staleness",
    responses={**UNAUTHORIZED},
)
def hq_heartbeats(
    svc: HQService = Depends(get_hq_service),
    _: object = Depends(require_view),
) -> Envelope:
    snap = svc.get_snapshot()
    return ok(snap["heartbeats"], _meta(snap))
