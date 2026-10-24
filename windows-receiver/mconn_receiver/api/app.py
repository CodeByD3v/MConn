"""FastAPI application factory. Routes follow DESIGN.md section 5."""
from __future__ import annotations

import asyncio
import json
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ..config import Settings
from ..database.db import Database
from ..errors import MConnError
from ..net import candidate_ips
from ..pairing.service import Identity, PairingService
from ..storage.store import InboxStore
from ..transfer.service import TransferService
from .admin import build_admin_router
from .auth import Authenticator


def _json(body: bytes) -> dict:
    try:
        data = json.loads(body or b"{}")
    except ValueError:
        raise MConnError(400, "INVALID_REQUEST", "Body must be valid JSON") from None
    if not isinstance(data, dict):
        raise MConnError(400, "INVALID_REQUEST", "Body must be a JSON object")
    return data


def create_app(settings: Settings, cert_sha256: str = "", admin_allowed_hosts: set[str] | None = None) -> FastAPI:
    db = Database(settings.db_path)
    pc_id = db.get_setting("pc_id")
    if not pc_id:
        pc_id = str(uuid.uuid4())
        db.set_setting("pc_id", pc_id)
    identity = Identity(
        pc_id=pc_id, pc_name=settings.pc_name, cert_sha256=cert_sha256, port=settings.port,
        hosts=settings.advertise_hosts if settings.advertise_hosts is not None else candidate_ips(),
    )
    store = InboxStore(settings)
    pairing = PairingService(db, settings, identity)
    transfers = TransferService(db, settings, store)
    auth = Authenticator(db, settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        transfers.reconcile()

        async def janitor() -> None:
            while True:
                await asyncio.sleep(3600)
                transfers.reconcile()

        task = asyncio.create_task(janitor())
        yield
        task.cancel()

    app = FastAPI(title="MConn receiver", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.pairing, app.state.transfers, app.state.db, app.state.identity = pairing, transfers, db, identity

    @app.exception_handler(MConnError)
    async def _err(_: Request, exc: MConnError) -> JSONResponse:
        return JSONResponse(exc.body(), status_code=exc.status)

    app.include_router(build_admin_router(pairing, admin_allowed_hosts or {"127.0.0.1", "::1"}))

    @app.post("/v1/pair/claim")
    async def pair_claim(request: Request) -> dict:
        data = _json(await request.body())
        session_id = pairing.claim(data.get("token"), data.get("device_name"), data.get("public_key"))
        return await pairing.wait_for_decision(session_id)

    @app.get("/v1/device/status")
    async def device_status(request: Request) -> dict:
        device = auth.authenticate(request, b"")
        return {"pc_id": pc_id, "device_status": device["status"], "accepting": True}

    @app.post("/v1/transfers")
    async def create_transfer(request: Request) -> JSONResponse:
        body = await request.body()
        device = auth.authenticate(request, body)
        status, payload = transfers.create(device["device_id"], _json(body))
        return JSONResponse(payload, status_code=status)

    @app.put("/v1/transfers/{transfer_id}/content")
    async def put_content(transfer_id: str, request: Request) -> dict:
        device = auth.authenticate(request, None)  # streamed: UNSIGNED-PAYLOAD
        try:
            offset = int(request.headers.get("upload-offset", "0"))
        except ValueError:
            raise MConnError(400, "INVALID_REQUEST", "Upload-Offset must be an integer") from None
        if offset < 0:
            raise MConnError(400, "INVALID_REQUEST", "Upload-Offset must be >= 0")
        return await transfers.put_content(device["device_id"], transfer_id, offset, request.stream())

    @app.get("/v1/transfers/{transfer_id}")
    async def get_transfer(transfer_id: str, request: Request) -> dict:
        device = auth.authenticate(request, b"")
        return transfers.status(device["device_id"], transfer_id)

    @app.get("/v1/inbox")
    async def get_inbox(request: Request, limit: int = 20) -> dict:
        device = auth.authenticate(request, b"")
        return {"items": transfers.inbox(device["device_id"], limit)}

    return app
