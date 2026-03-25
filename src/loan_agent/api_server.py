from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from livekit import api
from livekit.api.twirp_client import TwirpError

from loan_agent.db import db_conn, init_db, now_utc_iso, seed_sample_data
from loan_agent.models import (
    CallLogItem,
    CustomerCallRequest,
    LoanDashboardItem,
    OutboundCallResponse,
)

load_dotenv()

app = FastAPI(title="Agentic Loan Calling API", version="0.1.0")
WEB_DIR = Path(__file__).resolve().parent.parent.parent / "web"

if WEB_DIR.exists():
    app.mount("/web", StaticFiles(directory=str(WEB_DIR)), name="web")


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise HTTPException(status_code=500, detail=f"Missing required env var: {name}")
    return value


def _build_room_name(loan_id: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"loan-{loan_id}-{ts}".lower()


def _log_call(
    customer_id: int | None,
    loan_id: int | None,
    status: str,
    room_name: str | None = None,
    dispatch_id: str | None = None,
    sip_participant_id: str | None = None,
    provider_code: str | None = None,
    provider_message: str | None = None,
) -> None:
    if customer_id is None or loan_id is None:
        return

    now = now_utc_iso()
    with db_conn() as conn:
        conn.execute(
            """
            INSERT INTO call_logs(
                customer_id, loan_id, room_name, dispatch_id, sip_participant_id, status,
                provider_code, provider_message, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                customer_id,
                loan_id,
                room_name,
                dispatch_id,
                sip_participant_id,
                status,
                provider_code,
                provider_message,
                now,
                now,
            ),
        )


def _fetch_loan_row(loan_id: int):
    with db_conn() as conn:
        row = conn.execute(
            """
            SELECT
                l.id AS loan_id,
                l.loan_number,
                l.emi_amount,
                l.emi_status,
                l.due_date,
                c.id AS customer_id,
                c.name AS customer_name,
                c.phone_number,
                c.preferred_language
            FROM loans l
            JOIN customers c ON c.id = l.customer_id
            WHERE l.id = ?
            """,
            (loan_id,),
        ).fetchone()
    return row


async def _start_outbound_call(
    payload: CustomerCallRequest,
    customer_id: int | None = None,
    loan_id: int | None = None,
) -> OutboundCallResponse:
    agent_name = os.getenv("AGENT_DISPATCH_NAME", "loan-recovery-agent")
    sip_outbound_trunk_id = _required_env("LIVEKIT_SIP_OUTBOUND_TRUNK_ID")

    room_name = _build_room_name(payload.loan_id)

    metadata = {
        "customer_name": payload.customer_name,
        "loan_id": payload.loan_id,
        "loan_number": payload.loan_number,
        "emi_amount": payload.emi_amount,
        "emi_status": payload.emi_status,
        "due_date": payload.due_date,
        "language_hint": payload.language_hint,
    }

    try:
        async with api.LiveKitAPI() as lkapi:
            await lkapi.room.create_room(
                api.CreateRoomRequest(
                    name=room_name,
                    empty_timeout=10 * 60,
                    max_participants=5,
                    metadata=json.dumps(metadata),
                )
            )

            dispatch = await lkapi.agent_dispatch.create_dispatch(
                api.CreateAgentDispatchRequest(
                    agent_name=agent_name,
                    room=room_name,
                    metadata=json.dumps(metadata),
                )
            )

            sip_result = await lkapi.sip.create_sip_participant(
                api.CreateSIPParticipantRequest(
                    sip_trunk_id=sip_outbound_trunk_id,
                    sip_call_to=payload.phone_number,
                    room_name=room_name,
                    participant_identity=f"customer-{payload.loan_id}",
                    participant_name=payload.customer_name,
                    participant_metadata=json.dumps(metadata),
                    wait_until_answered=True,
                    ringing_timeout=timedelta(seconds=40),
                    play_dialtone=False,
                )
            )
    except TwirpError as error:
        _log_call(
            customer_id=customer_id,
            loan_id=loan_id,
            status="failed",
            room_name=room_name,
            provider_code=error.code,
            provider_message=error.message,
        )
        raise HTTPException(
            status_code=400,
            detail={
                "provider": "livekit",
                "code": error.code,
                "message": error.message,
                "status": error.status,
            },
        ) from error

    response = OutboundCallResponse(
        room_name=room_name,
        dispatch_id=dispatch.id,
        sip_participant_id=getattr(sip_result, "participant_identity", None),
    )

    _log_call(
        customer_id=customer_id,
        loan_id=loan_id,
        status="initiated",
        room_name=response.room_name,
        dispatch_id=response.dispatch_id,
        sip_participant_id=response.sip_participant_id,
    )

    return response


@app.on_event("startup")
async def startup_event() -> None:
    init_db()
    seed_sample_data()


@app.get("/")
async def root_dashboard():
    index_file = WEB_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="Dashboard file not found")
    return FileResponse(index_file)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/dashboard/loans", response_model=list[LoanDashboardItem])
async def get_dashboard_loans() -> list[LoanDashboardItem]:
    with db_conn() as conn:
        rows = conn.execute(
            """
            SELECT
                c.id AS customer_id,
                c.name AS customer_name,
                c.phone_number,
                c.preferred_language,
                l.id AS loan_id,
                l.loan_number,
                l.loan_amount,
                l.emi_amount,
                l.emi_status,
                l.due_date
            FROM loans l
            JOIN customers c ON c.id = l.customer_id
            ORDER BY l.id ASC
            """
        ).fetchall()

    return [LoanDashboardItem(**dict(row)) for row in rows]


@app.get("/api/calls", response_model=list[CallLogItem])
async def get_call_logs() -> list[CallLogItem]:
    with db_conn() as conn:
        rows = conn.execute(
            """
            SELECT
                cl.id,
                c.name AS customer_name,
                l.loan_number,
                cl.room_name,
                cl.dispatch_id,
                cl.status,
                cl.provider_code,
                cl.provider_message,
                cl.promised_payment_date,
                cl.created_at
            FROM call_logs cl
            JOIN customers c ON c.id = cl.customer_id
            JOIN loans l ON l.id = cl.loan_id
            ORDER BY cl.id DESC
            LIMIT 100
            """
        ).fetchall()

    return [CallLogItem(**dict(row)) for row in rows]


@app.post("/api/loans/{loan_id}/call", response_model=OutboundCallResponse)
async def trigger_call_for_loan(loan_id: int) -> OutboundCallResponse:
    row = _fetch_loan_row(loan_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Loan not found: {loan_id}")

    payload = CustomerCallRequest(
        phone_number=row["phone_number"],
        customer_name=row["customer_name"],
        loan_id=str(row["loan_id"]),
        loan_number=row["loan_number"],
        emi_amount=f"₹{int(row['emi_amount'])}",
        emi_status=row["emi_status"],
        due_date=row["due_date"],
        language_hint=row["preferred_language"],
    )

    return await _start_outbound_call(
        payload=payload,
        customer_id=row["customer_id"],
        loan_id=row["loan_id"],
    )


@app.post("/calls/outbound", response_model=OutboundCallResponse)
async def create_outbound_call(payload: CustomerCallRequest) -> OutboundCallResponse:
    with db_conn() as conn:
        row = conn.execute(
            """
            SELECT l.id AS loan_id, c.id AS customer_id
            FROM loans l
            JOIN customers c ON c.id = l.customer_id
            WHERE l.loan_number = ?
            """,
            (payload.loan_number,),
        ).fetchone()

    customer_id = row["customer_id"] if row else None
    loan_id = row["loan_id"] if row else None
    return await _start_outbound_call(payload, customer_id=customer_id, loan_id=loan_id)


@app.post("/webhooks/twilio/status")
async def twilio_status_webhook(
    call_sid: str = Form(alias="CallSid"),
    call_status: str = Form(alias="CallStatus"),
) -> dict[str, str]:
    return {"received": "true", "call_sid": call_sid, "call_status": call_status}
