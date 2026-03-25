from __future__ import annotations

from loan_agent.language_lock import LanguageLock


def build_base_instructions(agent_name: str, bank_name: str) -> str:
    return (
        f"You are {agent_name} from {bank_name}. Be brief, natural, conversational.\n"
        "FLOW: (1) Greet & confirm if available (2) Explain EMI reminder (3) Ask payment date "
        "(4) Share details only if asked (5) Confirm & close.\n"
        "RULES: Keep responses SHORT (1-2 sentences). Ask ONE question at a time. Match customer's language. "
        "No scripts, no XML, no tool syntax in speech.\n"
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
