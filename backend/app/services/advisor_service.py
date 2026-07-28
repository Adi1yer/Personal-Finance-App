"""Financial advisor chat with Ollama, tool loop, and multi-conversation history."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from sqlalchemy.orm import Session

from app.models.advisor_action_log import AdvisorActionLog
from app.models.advisor_chat_message import AdvisorChatMessage
from app.models.advisor_conversation import AdvisorConversation
from app.services.advisor_tools import execute_tool, is_action_tool, tool_definitions
from app.services.annual_goals import get_annual_goals_progress
from app.services.ollama_client import OllamaError, chat_message, ollama_base_url, ollama_model
from app.services.profile_settings import get_all_settings
from app.services.sync_health import build_health_summary

SYSTEM_PROMPT = """You are a private personal-finance advisor for this user's local ledger app.
You also help them set up and navigate the app (Plaid bank link, Google Drive backups, Ollama, goals).

Follow these rules strictly:
1. Answer the user's actual question. Do not dump balances, goals, or summaries unless they asked for them.
2. Greetings and questions about your purpose/capabilities: reply briefly in plain language. Mention you can help with finances and setup (bank, Drive, local AI). Do not call tools and do not cite any numbers.
3. For concrete financial questions (balances, goals, holdings, projections, duplicates, categories, or opinions on their finances): call tools first.
4. For setup / how-to questions (connect bank, Plaid keys, Google Drive, Ollama, where Settings is): call get_setup_status first, then give clear step-by-step guidance.
5. Numbers must come from tool results. Copy dollar amounts exactly from tool fields or quote_exactly. Never invent, estimate, or recompute shortfalls — use shortfall_vs_pace, remaining_to_annual, shortfall_vs_target when present.
6. Be concise — usually 2–6 short sentences unless the user asks for detail or a how-to walkthrough.
7. If the request is ambiguous, ask one clarifying question instead of guessing.
8. Only propose data changes when the user asks to change something; write actions need approval.
9. Reply with the answer text only — never prefix with role labels like "assistant".

You can help with: net worth / cash / debt overview, holdings, investment projections, annual investing & safety-net goals, duplicate transactions, balance mismatches, category rules (with approval), connecting Plaid, Google Drive backups, and checking whether Ollama/local AI is ready."""

MAX_TOOL_ROUNDS = 4
# Auto-compact long chats so Ollama stays efficient.
COMPACT_MIN_MESSAGES = 20
COMPACT_KEEP_RECENT = 10
COMPACT_CHAR_THRESHOLD = 14_000

_ROLE_PREFIX_RE = re.compile(
    r"^(?:assistant|user|system|Advisor)\s*:?\s*\n+",
    re.IGNORECASE,
)
_ROLE_INLINE_RE = re.compile(
    r"^(?:assistant|user|system|Advisor)\s*:\s*",
    re.IGNORECASE,
)
_DOLLAR_AMOUNT_RE = re.compile(r"\$\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)")
_MONEY_FIELD_KEYS = frozenset(
    {
        "annual_income",
        "annual_target",
        "ytd_actual",
        "pace_target",
        "shortfall_vs_pace",
        "ahead_of_pace",
        "remaining_to_annual",
        "target_balance",
        "current_balance",
        "shortfall_vs_target",
        "total",
        "market_value",
        "amount",
        "balance",
        "cash",
        "investments",
        "debt",
        "net_worth",
    }
)

# Meta / chit-chat — answer without tools or ledger dumps.
_CONVERSATIONAL_RE = re.compile(
    r"(?is)"
    r"(^\s*(hi|hello|hey|thanks|thank\s+you|good\s+(morning|afternoon|evening))\b)"
    r"|(\bwhat(?:'s|\s+is)\s+your\s+purpose\b)"
    r"|(\bwho\s+are\s+you\b)"
    r"|(\bwhat\s+can\s+you\s+(do|help(?:\s+with)?)\b)"
    r"|(\bwhat\s+do\s+you\s+do\b)"
    r"|(\byour\s+(purpose|role|job|capabilities)\b)"
    r"|(\bhow\s+(do\s+you\s+work|can\s+you\s+help)\b)"
    r"|(\bintroduce\s+yourself\b)"
    r"|(\btell\s+me\s+what\s+your\s+purpose\b)",
)

# Clear finance / setup intent — prefer tools.
_FINANCE_INTENT_RE = re.compile(
    r"(?is)"
    r"\b("
    r"balance|net\s*worth|cash|debt|invest|goal|projection|holding|portfolio|"
    r"duplicate|sync|spend|budget|category|rule|account|retirement|hsa|credit\s*card|"
    r"how\s+much|overview|summary|on\s+track|safety\s*net|"
    r"financ(?:e|es|ial)|situation|better|worse|opinion|advice|recommend|"
    r"plaid|google\s*drive|ollama|connect(?:\s+my)?\s+bank|backup|"
    r"set\s*up|setup|how\s+do\s+i\s+connect|oauth|encryption"
    r")\b",
)


def _clean_assistant_reply(text: str) -> str:
    """Strip role-echo prefixes some models prepend (e.g. leading 'assistant')."""
    t = (text or "").strip()
    # Repeat in case of "assistant\nassistant\n..."
    for _ in range(3):
        cleaned = _ROLE_PREFIX_RE.sub("", t)
        cleaned = _ROLE_INLINE_RE.sub("", cleaned).strip()
        if cleaned == t:
            break
        t = cleaned
    return t


def _norm_money(value: str | Decimal | float | int) -> str | None:
    try:
        return str(Decimal(str(value).replace(",", "")).quantize(Decimal("0.01")))
    except (InvalidOperation, ValueError):
        return None


def _collect_allowed_amounts(payload: Any, out: set[str], *, key: str | None = None) -> None:
    """Harvest money values from tool JSON for reply verification."""
    if isinstance(payload, dict):
        for k, v in payload.items():
            _collect_allowed_amounts(v, out, key=str(k))
        return
    if isinstance(payload, list):
        for v in payload:
            _collect_allowed_amounts(v, out, key=key)
        return
    if isinstance(payload, bool):
        return

    # Always accept $-annotated strings (e.g. quote_exactly lines).
    if isinstance(payload, str):
        for m in _DOLLAR_AMOUNT_RE.finditer(payload):
            n = _norm_money(m.group(1))
            if n is not None:
                out.add(n)
        if key in _MONEY_FIELD_KEYS:
            n = _norm_money(payload)
            if n is not None and Decimal(n) >= Decimal("1"):
                out.add(n)
        return

    if key in _MONEY_FIELD_KEYS and isinstance(payload, (int, float, Decimal)):
        n = _norm_money(payload)
        if n is not None and Decimal(n) >= Decimal("1"):
            out.add(n)


def _amount_is_allowed(norm: str, allowed: set[str]) -> bool:
    if norm in allowed:
        return True
    try:
        d = Decimal(norm)
    except InvalidOperation:
        return False
    for a in allowed:
        try:
            ad = Decimal(a)
        except InvalidOperation:
            continue
        # Allow whole-dollar rounding of a known tool figure.
        if abs(ad - d) <= Decimal("1.00"):
            return True
        if d == ad.to_integral_value(rounding=ROUND_HALF_UP) or ad == d.to_integral_value(
            rounding=ROUND_HALF_UP
        ):
            return True
    return False


def _invented_dollar_amounts(reply: str, allowed: set[str]) -> list[str]:
    """Return $-amounts in the reply that are not grounded in tool results."""
    if not allowed:
        return []
    bad: list[str] = []
    for m in _DOLLAR_AMOUNT_RE.finditer(reply or ""):
        norm = _norm_money(m.group(1))
        if norm is None:
            continue
        if Decimal(norm) < Decimal("1"):
            continue
        if not _amount_is_allowed(norm, allowed):
            bad.append(norm)
    return bad


def _is_conversational(message: str) -> bool:
    """True for greetings / purpose questions that should not trigger finance tools."""
    text = (message or "").strip()
    if not text:
        return True
    has_meta = bool(_CONVERSATIONAL_RE.search(text))
    has_finance = bool(_FINANCE_INTENT_RE.search(text))
    # Any concrete finance ask wins — even if the message also says hello.
    if has_finance:
        return False
    return has_meta


def _last_user_content(messages: list[dict[str, Any]]) -> str:
    for m in reversed(messages):
        if m.get("role") == "user":
            return str(m.get("content") or "")
    return ""


def _build_chat_messages(
    *,
    prior: list[dict[str, Any]],
    user_message: str | None,
    page_context: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Build the Ollama message list. Avoid dumping ledger JSON into every turn."""
    messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    if page_context:
        messages.append(
            {
                "role": "system",
                "content": (
                    "UI page context (only use if relevant to the question): "
                    f"{json.dumps(page_context, default=str)}"
                ),
            }
        )
    messages.extend(_llm_history(prior))
    if user_message is not None:
        messages.append({"role": "user", "content": user_message})
    return messages


def _plain_conversational_reply(
    *,
    messages: list[dict[str, Any]],
    model: str,
    base_url: str,
) -> str:
    guided = [
        *messages,
        {
            "role": "system",
            "content": (
                "The user is greeting you or asking about your purpose/capabilities. "
                "Answer directly in a few sentences. Do not mention balances, goals, "
                "investments, or any dollar amounts."
            ),
        },
    ]
    msg = chat_message(guided, model=model, base_url=base_url, tools=None)
    return _clean_assistant_reply(msg.get("content") or "")


def _context_packet(db: Session) -> dict[str, Any]:
    """Lightweight health flags (available to callers; not auto-injected into chat)."""
    health = build_health_summary(db)
    return {
        "health_ok": health["ok"],
        "duplicate_clusters": health["suspected_duplicate_clusters"],
        "balance_mismatches": len(health["balance_mismatches"]),
    }


def _touch_conversation(db: Session, conv: AdvisorConversation) -> None:
    conv.updated_at = datetime.now(timezone.utc)
    db.commit()


def list_conversations(db: Session) -> list[dict[str, Any]]:
    rows = (
        db.query(AdvisorConversation)
        .order_by(AdvisorConversation.updated_at.desc(), AdvisorConversation.id.desc())
        .all()
    )
    out: list[dict[str, Any]] = []
    for c in rows:
        msg_count = (
            db.query(AdvisorChatMessage)
            .filter(AdvisorChatMessage.conversation_id == c.id)
            .count()
        )
        out.append(
            {
                "id": c.id,
                "title": c.title,
                "updated_at": c.updated_at.isoformat() if c.updated_at else None,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "message_count": msg_count,
            }
        )
    return out


def create_conversation(db: Session, title: str = "New chat") -> dict[str, Any]:
    conv = AdvisorConversation(title=(title or "New chat").strip()[:120] or "New chat")
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return {
        "id": conv.id,
        "title": conv.title,
        "updated_at": conv.updated_at.isoformat() if conv.updated_at else None,
        "created_at": conv.created_at.isoformat() if conv.created_at else None,
        "message_count": 0,
    }


def rename_conversation(db: Session, conversation_id: int, title: str) -> dict[str, Any]:
    conv = db.get(AdvisorConversation, conversation_id)
    if not conv:
        raise ValueError("Conversation not found")
    cleaned = (title or "").strip()[:120]
    if not cleaned:
        raise ValueError("Title cannot be empty")
    conv.title = cleaned
    _touch_conversation(db, conv)
    db.refresh(conv)
    msg_count = (
        db.query(AdvisorChatMessage)
        .filter(AdvisorChatMessage.conversation_id == conversation_id)
        .count()
    )
    return {
        "id": conv.id,
        "title": conv.title,
        "updated_at": conv.updated_at.isoformat() if conv.updated_at else None,
        "created_at": conv.created_at.isoformat() if conv.created_at else None,
        "message_count": msg_count,
    }


def delete_conversation(db: Session, conversation_id: int) -> None:
    conv = db.get(AdvisorConversation, conversation_id)
    if not conv:
        raise ValueError("Conversation not found")
    db.query(AdvisorChatMessage).filter(
        AdvisorChatMessage.conversation_id == conversation_id
    ).delete()
    db.delete(conv)
    db.commit()


def get_conversation_messages(db: Session, conversation_id: int) -> list[dict[str, Any]]:
    conv = db.get(AdvisorConversation, conversation_id)
    if not conv:
        raise ValueError("Conversation not found")
    rows = (
        db.query(AdvisorChatMessage)
        .filter(AdvisorChatMessage.conversation_id == conversation_id)
        .order_by(AdvisorChatMessage.id.asc())
        .all()
    )
    return [
        {
            "id": r.id,
            "role": r.role,
            "content": (
                _clean_assistant_reply(r.content) if r.role == "assistant" else r.content
            ),
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
        if r.role in ("user", "assistant", "summary") and (r.content or "").strip()
    ]


def _llm_history(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Map stored messages (including summary) into Ollama chat roles."""
    out: list[dict[str, str]] = []
    for m in rows:
        role = m["role"]
        content = m["content"]
        if role == "summary":
            out.append(
                {
                    "role": "system",
                    "content": f"Compressed memory of earlier turns in this chat:\n{content}",
                }
            )
        elif role in ("user", "assistant"):
            out.append({"role": role, "content": content})
    return out


def maybe_compact_conversation(
    db: Session,
    conversation_id: int,
    *,
    model: str,
    base_url: str,
) -> bool:
    """Summarize older turns into one summary message when history is large."""
    rows = (
        db.query(AdvisorChatMessage)
        .filter(AdvisorChatMessage.conversation_id == conversation_id)
        .order_by(AdvisorChatMessage.id.asc())
        .all()
    )
    dialogue = [r for r in rows if r.role in ("user", "assistant", "summary") and (r.content or "").strip()]
    if len(dialogue) < COMPACT_MIN_MESSAGES:
        return False
    total_chars = sum(len(r.content or "") for r in dialogue)
    if total_chars < COMPACT_CHAR_THRESHOLD and len(dialogue) < COMPACT_MIN_MESSAGES + 8:
        return False

    keep = dialogue[-COMPACT_KEEP_RECENT:]
    older = dialogue[:-COMPACT_KEEP_RECENT]
    if not older:
        return False

    transcript_parts: list[str] = []
    for r in older:
        label = "MEMORY" if r.role == "summary" else r.role.upper()
        transcript_parts.append(f"{label}: {r.content}")
    transcript = "\n".join(transcript_parts)[:24_000]

    try:
        msg = chat_message(
            [
                {
                    "role": "system",
                    "content": (
                        "Compress this personal-finance chat history into a concise memory note. "
                        "Keep goals, numbers, decisions, open questions, and user preferences. "
                        "Omit chit-chat. Max ~250 words. Plain text only."
                    ),
                },
                {"role": "user", "content": transcript},
            ],
            model=model,
            base_url=base_url,
            tools=None,
        )
        summary = (msg.get("content") or "").strip()
    except OllamaError:
        summary = "Earlier conversation (auto-truncated):\n" + "\n".join(
            f"- {r.role}: {(r.content or '')[:160]}" for r in older[-12:]
        )

    if not summary:
        return False

    keep_ids = {r.id for r in keep}
    for r in rows:
        if r.id not in keep_ids:
            db.delete(r)
    db.commit()

    recent_payload = [{"role": r.role, "content": r.content} for r in keep]
    for r in keep:
        db.delete(r)
    db.commit()

    _save_message(db, conversation_id, "summary", summary)
    for item in recent_payload:
        _save_message(db, conversation_id, item["role"], item["content"])
    return True


def _delete_messages_after(db: Session, conversation_id: int, message_id: int) -> None:
    later = (
        db.query(AdvisorChatMessage)
        .filter(
            AdvisorChatMessage.conversation_id == conversation_id,
            AdvisorChatMessage.id > message_id,
        )
        .all()
    )
    for row in later:
        db.delete(row)
    db.commit()


def _generate_assistant_reply(
    db: Session,
    conversation_id: int,
    *,
    model: str,
    base_url: str,
    page_context: dict[str, Any] | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """Generate an assistant reply from current conversation history (no new user msg)."""
    prior = get_conversation_messages(db, conversation_id)
    user_message = _last_user_content(prior)
    messages = _build_chat_messages(
        prior=prior, user_message=None, page_context=page_context
    )

    try:
        if _is_conversational(user_message):
            reply = _plain_conversational_reply(
                messages=messages, model=model, base_url=base_url
            )
            pending: list[dict[str, Any]] = []
        else:
            reply, pending = _run_tool_loop(
                db, messages=messages, model=model, base_url=base_url
            )
    except OllamaError as e:
        reply = f"Advisor error talking to Ollama: {e}"
        pending = []
    reply = _clean_assistant_reply(reply)
    if not reply:
        reply = "I didn't get a usable reply from the local model. Check Ollama and try again."
    return reply, pending


def list_chat_history(db: Session, limit: int = 50) -> list[dict[str, str]]:
    """Legacy flat history — newest conversation messages."""
    conv = (
        db.query(AdvisorConversation)
        .order_by(AdvisorConversation.updated_at.desc())
        .first()
    )
    if not conv:
        return []
    msgs = get_conversation_messages(db, conv.id)
    return [{"role": m["role"], "content": m["content"]} for m in msgs[-limit:]]


def _save_message(db: Session, conversation_id: int, role: str, content: str) -> AdvisorChatMessage:
    row = AdvisorChatMessage(
        conversation_id=conversation_id,
        role=role,
        content=content,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _title_from_message(message: str) -> str:
    cleaned = " ".join((message or "").strip().split())
    if not cleaned:
        return "New chat"
    return (cleaned[:60] + "…") if len(cleaned) > 60 else cleaned


def _normalize_tool_calls(tool_calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for i, call in enumerate(tool_calls or []):
        fn = call.get("function") or {}
        name = fn.get("name") or call.get("name")
        raw_args = fn.get("arguments", call.get("arguments", {}))
        if isinstance(raw_args, str):
            try:
                args = json.loads(raw_args) if raw_args.strip() else {}
            except json.JSONDecodeError:
                args = {}
        elif isinstance(raw_args, dict):
            args = raw_args
        else:
            args = {}
        if not name:
            continue
        normalized.append(
            {
                "id": call.get("id") or f"call_{i}",
                "name": name,
                "arguments": args,
            }
        )
    return normalized


def _looks_like_broken_tool_json(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return True
    if t.startswith("{") and ("function" in t or "tool_calls" in t or "parameters" in t):
        return True
    if t.startswith('{"type": "function"'):
        return True
    return False


def _run_tool_loop(
    db: Session,
    *,
    messages: list[dict[str, Any]],
    model: str,
    base_url: str,
) -> tuple[str, list[dict[str, Any]]]:
    """Execute Ollama tool calls until a final text reply. Returns (reply, pending_actions)."""
    pending_actions: list[dict[str, Any]] = []
    tools = tool_definitions()
    working = list(messages)
    allowed_amounts: set[str] = set()
    quote_sheets: list[str] = []

    for _ in range(MAX_TOOL_ROUNDS):
        msg = chat_message(working, model=model, base_url=base_url, tools=tools)
        content = (msg.get("content") or "").strip()
        tool_calls = _normalize_tool_calls(msg.get("tool_calls") or [])

        if not tool_calls:
            if _looks_like_broken_tool_json(content):
                # llama3.1 sometimes emits fake tool JSON in content — retry plain chat.
                plain_msgs = [
                    *messages,
                    {
                        "role": "system",
                        "content": "Reply in plain natural language only. Do not output JSON or function calls.",
                    },
                ]
                final = chat_message(plain_msgs, model=model, base_url=base_url, tools=None)
                text = _clean_assistant_reply(final.get("content") or "")
                if text and not _looks_like_broken_tool_json(text):
                    return _maybe_correct_numbers(
                        text,
                        working=working,
                        allowed_amounts=allowed_amounts,
                        quote_sheets=quote_sheets,
                        model=model,
                        base_url=base_url,
                    ), pending_actions
            if content and not _looks_like_broken_tool_json(content):
                return _maybe_correct_numbers(
                    _clean_assistant_reply(content),
                    working=working,
                    allowed_amounts=allowed_amounts,
                    quote_sheets=quote_sheets,
                    model=model,
                    base_url=base_url,
                ), pending_actions
            break

        working.append(
            {
                "role": "assistant",
                "content": content,
                "tool_calls": msg.get("tool_calls") or [],
            }
        )

        for call in tool_calls:
            name = call["name"]
            args = call["arguments"]
            if is_action_tool(name):
                action = propose_action(db, name, args)
                pending_actions.append(action)
                result: Any = {
                    "status": "pending_approval",
                    "action_id": action["action_id"],
                    "message": f"Proposed {name}; waiting for user approval.",
                }
            else:
                try:
                    result = execute_tool(db, name, args)
                except Exception as e:
                    result = {"error": str(e)}
            _collect_allowed_amounts(result, allowed_amounts)
            if isinstance(result, dict):
                quotes = result.get("quote_exactly")
                if isinstance(quotes, list):
                    quote_sheets.extend(str(q) for q in quotes)
            working.append(
                {
                    "role": "tool",
                    "tool_name": name,
                    "content": json.dumps(result, default=str),
                }
            )

    final = chat_message(
        [
            *working,
            {
                "role": "system",
                "content": (
                    "Answer ONLY the user's latest question in clear plain language. "
                    "Copy dollar amounts exactly from tool results / quote_exactly. "
                    "Do not invent, estimate, or recompute shortfalls. "
                    "Do not volunteer unrelated balances. "
                    "Do not prefix with 'assistant'."
                ),
            },
        ],
        model=model,
        base_url=base_url,
        tools=None,
    )
    text = _clean_assistant_reply(final.get("content") or "")
    if _looks_like_broken_tool_json(text):
        text = ""
    if text:
        text = _maybe_correct_numbers(
            text,
            working=working,
            allowed_amounts=allowed_amounts,
            quote_sheets=quote_sheets,
            model=model,
            base_url=base_url,
        )
    if not text and pending_actions:
        text = (
            "I prepared action(s) that need your approval before changing data. "
            "Review them below."
        )
    return (
        text
        or "I gathered some data but couldn't summarize it. Ask me again more specifically.",
        pending_actions,
    )


def _maybe_correct_numbers(
    reply: str,
    *,
    working: list[dict[str, Any]],
    allowed_amounts: set[str],
    quote_sheets: list[str],
    model: str,
    base_url: str,
) -> str:
    """If the model cited $-amounts not in tool data, force one grounded rewrite."""
    bad = _invented_dollar_amounts(reply, allowed_amounts)
    if not bad:
        return reply
    facts = "\n".join(f"- {line}" for line in quote_sheets[:20]) or (
        "Use only dollar amounts present in the prior tool JSON."
    )
    corrected = chat_message(
        [
            *working,
            {"role": "assistant", "content": reply},
            {
                "role": "system",
                "content": (
                    "Your previous reply cited dollar amount(s) that are not in the tool data: "
                    f"{', '.join('$' + a for a in bad)}. "
                    "Rewrite the answer now. Copy figures exactly from these facts "
                    "(or other tool fields). Do not recalculate.\n"
                    f"{facts}"
                ),
            },
        ],
        model=model,
        base_url=base_url,
        tools=None,
    )
    text = _clean_assistant_reply(corrected.get("content") or "")
    if not text or _looks_like_broken_tool_json(text):
        return reply
    # If still inventing, prefer a deterministic fact dump over bad math.
    still_bad = _invented_dollar_amounts(text, allowed_amounts)
    if still_bad and quote_sheets:
        return (
            "Here are the ledger figures (exact):\n"
            + "\n".join(f"• {line}" for line in quote_sheets[:8])
            + "\n\nI can go deeper on any of these if you want."
        )
    return text


def chat_with_advisor(
    db: Session,
    user_message: str,
    *,
    conversation_id: int | None = None,
    page_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    settings = get_all_settings(db)
    model = ollama_model(settings)
    base_url = ollama_base_url(settings)

    if conversation_id is None:
        conv_data = create_conversation(db, _title_from_message(user_message))
        conversation_id = int(conv_data["id"])
    conv = db.get(AdvisorConversation, conversation_id)
    if not conv:
        raise ValueError("Conversation not found")

    # Rename default title from first user message.
    if conv.title in ("New chat", "Previous chat") or not conv.title:
        conv.title = _title_from_message(user_message)

    compacted = maybe_compact_conversation(
        db, conversation_id, model=model, base_url=base_url
    )

    prior = get_conversation_messages(db, conversation_id)
    messages = _build_chat_messages(
        prior=prior,
        user_message=user_message,
        page_context=page_context,
    )
    _save_message(db, conversation_id, "user", user_message)

    try:
        if _is_conversational(user_message):
            reply = _plain_conversational_reply(
                messages=messages, model=model, base_url=base_url
            )
            pending: list[dict[str, Any]] = []
        else:
            reply, pending = _run_tool_loop(
                db, messages=messages, model=model, base_url=base_url
            )
    except OllamaError as e:
        reply = f"Advisor error talking to Ollama: {e}"
        pending = []

    if not (reply or "").strip():
        reply = "I didn't get a usable reply from the local model. Check Ollama and try again."
    else:
        reply = _clean_assistant_reply(reply)

    assistant_row = _save_message(db, conversation_id, "assistant", reply)
    _touch_conversation(db, conv)

    return {
        "conversation_id": conversation_id,
        "reply": reply,
        "message_id": assistant_row.id,
        "pending_actions": pending,
        "title": conv.title,
        "compacted": compacted,
    }


def edit_message(
    db: Session,
    conversation_id: int,
    message_id: int,
    new_content: str,
    *,
    fork: bool = False,
    page_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Edit a user message, drop later turns (or fork into a new chat), and regenerate."""
    content = (new_content or "").strip()
    if not content:
        raise ValueError("Message cannot be empty")

    src = db.get(AdvisorChatMessage, message_id)
    if not src or src.conversation_id != conversation_id:
        raise ValueError("Message not found")
    if src.role != "user":
        raise ValueError("Only user messages can be edited")

    settings = get_all_settings(db)
    model = ollama_model(settings)
    base_url = ollama_base_url(settings)
    target_conversation_id = conversation_id

    if fork:
        parent = db.get(AdvisorConversation, conversation_id)
        if not parent:
            raise ValueError("Conversation not found")
        fork_conv = create_conversation(db, f"Fork: {_title_from_message(content)}")
        target_conversation_id = int(fork_conv["id"])

        earlier = (
            db.query(AdvisorChatMessage)
            .filter(
                AdvisorChatMessage.conversation_id == conversation_id,
                AdvisorChatMessage.id < message_id,
            )
            .order_by(AdvisorChatMessage.id.asc())
            .all()
        )
        for row in earlier:
            if row.role in ("user", "assistant", "summary") and (row.content or "").strip():
                _save_message(db, target_conversation_id, row.role, row.content)
        _save_message(db, target_conversation_id, "user", content)
    else:
        _delete_messages_after(db, conversation_id, message_id)
        src.content = content
        db.add(src)
        db.commit()
        db.refresh(src)

    compacted = maybe_compact_conversation(
        db, target_conversation_id, model=model, base_url=base_url
    )
    reply, pending = _generate_assistant_reply(
        db,
        target_conversation_id,
        model=model,
        base_url=base_url,
        page_context=page_context,
    )
    assistant_row = _save_message(db, target_conversation_id, "assistant", reply)
    conv = db.get(AdvisorConversation, target_conversation_id)
    if conv:
        if not fork and conv.title in ("New chat", "Previous chat"):
            conv.title = _title_from_message(content)
        _touch_conversation(db, conv)

    return {
        "conversation_id": target_conversation_id,
        "reply": reply,
        "message_id": assistant_row.id,
        "pending_actions": pending,
        "title": conv.title if conv else None,
        "compacted": compacted,
        "forked": fork,
    }


def propose_action(db: Session, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    log = AdvisorActionLog(
        tool_name=tool_name,
        args_json=json.dumps(args),
        approved=False,
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return {
        "action_id": log.id,
        "tool_name": tool_name,
        "args": args,
        "requires_approval": is_action_tool(tool_name),
    }


def approve_action(db: Session, action_id: int, approved: bool) -> dict[str, Any]:
    log = db.get(AdvisorActionLog, action_id)
    if not log:
        raise ValueError("Action not found")
    log.approved = approved
    if not approved:
        db.commit()
        return {"status": "rejected", "action_id": action_id}
    args = json.loads(log.args_json or "{}")
    result = execute_tool(db, log.tool_name, args)
    log.result_json = json.dumps(result, default=str)
    db.commit()
    return {"status": "approved", "action_id": action_id, "result": result}


def sync_insights(db: Session) -> list[str]:
    health = build_health_summary(db)
    goals = get_annual_goals_progress(db)
    bullets: list[str] = []
    if health["suspected_duplicate_clusters"]:
        bullets.append(
            f"{health['suspected_duplicate_clusters']} suspected duplicate(s) — review in Duplicates."
        )
    if health["balance_mismatches"]:
        bullets.append(f"{len(health['balance_mismatches'])} balance mismatch(es) detected.")
    if not goals["investing"]["on_track"]:
        bullets.append("Investing goal is behind pace for the year.")
    if not bullets:
        bullets.append("Sync complete — ledger looks healthy.")
    return bullets[:3]
