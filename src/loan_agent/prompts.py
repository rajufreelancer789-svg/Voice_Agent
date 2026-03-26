from __future__ import annotations

from loan_agent.language_lock import LanguageLock


def build_base_instructions(agent_name: str, bank_name: str) -> str:
    return (
        f"You are {agent_name}, {bank_name} debt recovery agent.\n"
        "Be brief (1-2 sentences per response). No scripts or XML.\n"
        "FLOW: Greet → Explain EMI reminder → Ask payment date → Confirm → Close.\n"
    )


def build_runtime_instructions(
    language_lock: LanguageLock,
    customer_name: str,
    loan_number: str,
    emi_amount: str,
    due_date: str,
    emi_status: str,
) -> str:
    return (
        f"Customer: {customer_name} | Loan#: {loan_number} | Amount: {emi_amount} | Due: {due_date} | Status: {emi_status}\n"
        f"{language_lock.system_rule()}\n"
        "START: Greet in English. Ask if speaking with customer_name. Ask if it's a good time to talk."
    )
