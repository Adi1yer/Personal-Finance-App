"""Tool implementations for the financial advisor."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.services.annual_goals import get_annual_goals_progress
from app.services.balance_explain import explain_balance
from app.services.categorization import create_rule
from app.services.duplicate_review import list_suspected_clusters, merge_cluster
from app.services.holdings import list_holdings
from app.services.overview import build_overview
from app.services.projection_engine import run_projection

ACTION_TOOLS = frozenset(
    {
        "merge_duplicates",
        "create_category_rule",
        "categorize_entry",
        "mark_staging_skipped",
    }
)


def _money(value: str | Decimal | float | int) -> str:
    return str(Decimal(str(value)).quantize(Decimal("0.01")))


def _goals_quote_sheet(goals: dict[str, Any]) -> list[str]:
    """Precomputed sentences the model should copy — avoids LLM arithmetic errors."""
    inv = goals["investing"]
    sn = goals["safety_net"]
    month = goals["month"]
    year = goals["year"]
    return [
        f"Annual income basis: ${_money(goals['annual_income'])} ({goals['income_source']}).",
        (
            f"Investing goal: {inv['pct_of_income']}% of income → "
            f"annual target ${_money(inv['annual_target'])}."
        ),
        f"Invested year-to-date ({year}): ${_money(inv['ytd_actual'])}.",
        (
            f"Pace target through month {month}/12: ${_money(inv['pace_target'])} "
            f"(on_track={inv['on_track']})."
        ),
        f"Shortfall vs pace: ${_money(inv['shortfall_vs_pace'])}.",
        f"Remaining to hit full annual investing target: ${_money(inv['remaining_to_annual'])}.",
        (
            f"Safety net: current ${_money(sn['current_balance'])} vs target "
            f"${_money(sn['target_balance'])} (shortfall ${_money(sn['shortfall_vs_target'])}, "
            f"on_track={sn['on_track']})."
        ),
    ]


def tool_definitions() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "get_financial_summary",
                "description": (
                    "Fetch net worth groups and annual goal progress with precomputed shortfalls. "
                    "Use when the user asks for an overview, balances, goals, opinions on finances, "
                    "or how they are tracking. Prefer quote_exactly figures — do not recalculate."
                ),
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_holdings",
                "description": "List holdings for an investment account when the user asks about positions/tickers.",
                "parameters": {
                    "type": "object",
                    "properties": {"account_id": {"type": "integer"}},
                    "required": ["account_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "run_projection",
                "description": "Run dividend/portfolio projection when the user asks about future growth or projections.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "horizon_years": {"type": "integer"},
                        "stock_appreciation_pct": {"type": "number"},
                        "dividend_growth_pct": {"type": "number"},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_suspected_dupes",
                "description": "List duplicate transaction clusters when the user asks about duplicates.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "explain_balance",
                "description": "Explain ledger vs Plaid balance for an account when the user asks why a balance looks wrong.",
                "parameters": {
                    "type": "object",
                    "properties": {"account_id": {"type": "integer"}},
                    "required": ["account_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "merge_duplicates",
                "description": "Merge duplicate cluster (requires approval). Only when the user asks to merge duplicates.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "cluster_id": {"type": "integer"},
                        "keep_transaction_id": {"type": "integer"},
                    },
                    "required": ["cluster_id", "keep_transaction_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "create_category_rule",
                "description": "Create categorization rule (requires approval). Only when the user asks to create a rule.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "pattern": {"type": "string"},
                        "category_id": {"type": "integer"},
                    },
                    "required": ["pattern", "category_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_setup_status",
                "description": (
                    "Check what is configured locally: encryption key, Plaid, Google Drive OAuth, "
                    "and redirect URIs. Use for setup / how-to questions about connecting a bank, "
                    "Drive backups, or missing credentials."
                ),
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_plaid_connection_status",
                "description": "Whether Plaid is enabled and how many bank items are linked for this profile.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_google_drive_status",
                "description": "Whether Google Drive backup is configured and connected for this profile.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_help_guides",
                "description": (
                    "List packaged setup help guides (install, Plaid, Google Drive, accounts, "
                    "goals, Ollama, troubleshooting). Use for setup walkthroughs."
                ),
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_help_guides",
                "description": (
                    "Search setup help docs by keywords (e.g. 'google drive test user', "
                    "'total contributions', 'safari certificate'). Prefer this before guessing."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "limit": {"type": "integer"},
                    },
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_help_guide",
                "description": (
                    "Read the full markdown of one help guide by slug "
                    "(e.g. '04-plaid-bank-connect', '05-google-drive-backups', 'README'). "
                    "Use after list_help_guides or search_help_guides."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {"slug": {"type": "string"}},
                    "required": ["slug"],
                },
            },
        },
    ]


def _get_financial_summary(db: Session, **_kwargs: Any) -> dict[str, Any]:
    overview = build_overview(db)
    goals = get_annual_goals_progress(db)
    groups = [{"key": g.key, "label": g.label, "total": str(g.total)} for g in overview.groups]
    quote_exactly = _goals_quote_sheet(goals)
    for g in groups:
        quote_exactly.append(f"{g['label']}: ${g['total']}.")
    return {
        "groups": groups,
        "goals": goals,
        "quote_exactly": quote_exactly,
        "number_rules": (
            "Copy dollar amounts from quote_exactly or goals/groups fields verbatim. "
            "Never invent, round aggressively, or recompute shortfalls — "
            "use shortfall_vs_pace, remaining_to_annual, and shortfall_vs_target as given."
        ),
    }


def _get_holdings(db: Session, account_id: int, **_kwargs: Any) -> list[dict[str, str]]:
    return [
        {
            "ticker": h.ticker,
            "quantity": str(h.quantity),
            "market_value": str(h.market_value or 0),
        }
        for h in list_holdings(db, account_id)
    ]


def _run_projection(db: Session, **kwargs: Any) -> dict[str, Any]:
    return run_projection(db, **{k: v for k, v in kwargs.items() if v is not None})


def _list_suspected_dupes(db: Session, **_kwargs: Any) -> list[dict[str, Any]]:
    return list_suspected_clusters(db)


def _explain_balance(db: Session, account_id: int, **_kwargs: Any) -> dict[str, Any]:
    return explain_balance(db, account_id)


def _merge_duplicates(db: Session, cluster_id: int, keep_transaction_id: int, **_kwargs: Any) -> dict[str, int]:
    return merge_cluster(db, cluster_id, keep_transaction_id)


def _create_category_rule(db: Session, pattern: str, category_id: int, **_kwargs: Any) -> dict[str, Any]:
    rule, applied = create_rule(db, pattern=pattern, category_id=category_id)
    return {"rule_id": rule.id, "transactions_updated": applied}


def _get_setup_status(db: Session, **_kwargs: Any) -> dict[str, Any]:
    from app.services.app_config import setup_status
    from app.services.ollama_client import health_check, ollama_base_url, ollama_model
    from app.services.profile_settings import get_all_settings

    status = setup_status()
    settings = get_all_settings(db)
    ollama = health_check(ollama_base_url(settings))
    status["ollama"] = {
        "connected": bool(ollama.get("connected")),
        "url": ollama_base_url(settings),
        "model": ollama_model(settings),
        "hint": "Install from https://ollama.com if offline; set URL/model under Settings.",
    }
    status["where_to_configure"] = (
        "Settings → Connections setup (Plaid + Google keys). "
        "Settings → Connect bank (Plaid Link). "
        "Settings → Google Drive backups. "
        "Settings → Preferences for Ollama URL/model. "
        "Settings → Setup help for the full guided checklist."
    )
    from app.services.help_docs import help_index_for_advisor

    status["docs"] = help_index_for_advisor()
    return status


def _get_plaid_connection_status(db: Session, **_kwargs: Any) -> dict[str, Any]:
    from app.services import plaid_sync

    return plaid_sync.plaid_status(db)


def _get_google_drive_status(db: Session, **_kwargs: Any) -> dict[str, Any]:
    from app.config import get_settings
    from app.services.google_drive_backup import connection_status

    out = connection_status(db)
    out["configured"] = get_settings().google_drive_configured
    return out


def _list_help_guides(db: Session, **_kwargs: Any) -> dict[str, Any]:
    from app.services.help_docs import help_index_for_advisor

    return help_index_for_advisor()


def _search_help_guides(db: Session, query: str, limit: int = 5, **_kwargs: Any) -> list[dict[str, Any]]:
    from app.services.help_docs import search_help_guides

    return search_help_guides(query, limit=limit or 5)


def _read_help_guide(db: Session, slug: str, **_kwargs: Any) -> dict[str, str]:
    from app.services.help_docs import read_help_guide

    return read_help_guide(slug)


TOOL_HANDLERS: dict[str, Callable[..., Any]] = {
    "get_financial_summary": _get_financial_summary,
    "get_holdings": _get_holdings,
    "run_projection": _run_projection,
    "list_suspected_dupes": _list_suspected_dupes,
    "explain_balance": _explain_balance,
    "merge_duplicates": _merge_duplicates,
    "create_category_rule": _create_category_rule,
    "get_setup_status": _get_setup_status,
    "get_plaid_connection_status": _get_plaid_connection_status,
    "get_google_drive_status": _get_google_drive_status,
    "list_help_guides": _list_help_guides,
    "search_help_guides": _search_help_guides,
    "read_help_guide": _read_help_guide,
}


def execute_tool(db: Session, name: str, args: dict[str, Any]) -> Any:
    handler = TOOL_HANDLERS.get(name)
    if not handler:
        raise ValueError(f"Unknown tool: {name}")
    return handler(db, **args)


def is_action_tool(name: str) -> bool:
    return name in ACTION_TOOLS
