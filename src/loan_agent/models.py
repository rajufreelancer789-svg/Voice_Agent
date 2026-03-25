from __future__ import annotations

from pydantic import BaseModel, Field


class CustomerCallRequest(BaseModel):
    phone_number: str = Field(..., description="E.164 number, e.g. +9198xxxxxx")
    customer_name: str
    loan_id: str
    loan_number: str
    emi_amount: str
    emi_status: str
    due_date: str
    language_hint: str | None = None


class OutboundCallResponse(BaseModel):
    room_name: str
    dispatch_id: str
    sip_participant_id: str | None = None
    status: str = "initiated"


class LoanDashboardItem(BaseModel):
    customer_id: int
    customer_name: str
    phone_number: str
    preferred_language: str | None = None
    loan_id: int
    loan_number: str
    loan_amount: float
    emi_amount: float
    emi_status: str
    due_date: str


class CallLogItem(BaseModel):
    id: int
    customer_name: str
    loan_number: str
    room_name: str | None = None
    dispatch_id: str | None = None
    status: str
    provider_code: str | None = None
    provider_message: str | None = None
    promised_payment_date: str | None = None
    created_at: str


class TriggerCallByLoanRequest(BaseModel):
    loan_id: int
