from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.services.advisor_service import (
    approve_action,
    chat_with_advisor,
    create_conversation,
    delete_conversation,
    edit_message,
    get_conversation_messages,
    list_conversations,
    propose_action,
    rename_conversation,
    sync_insights,
)

router = APIRouter(prefix="/advisor", tags=["advisor"])


class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[int] = None
    page_context: Optional[dict[str, Any]] = None


class ChatResponse(BaseModel):
    reply: str
    conversation_id: int
    message_id: Optional[int] = None
    pending_actions: list[dict[str, Any]] = []
    title: Optional[str] = None
    compacted: bool = False
    forked: bool = False


class ProposeActionRequest(BaseModel):
    tool_name: str
    args: dict[str, Any]


class ApproveActionRequest(BaseModel):
    approved: bool


class CreateConversationRequest(BaseModel):
    title: Optional[str] = "New chat"


class RenameConversationRequest(BaseModel):
    title: str


class EditMessageRequest(BaseModel):
    content: str
    fork: bool = False
    page_context: Optional[dict[str, Any]] = None


@router.get("/conversations")
def get_conversations(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return list_conversations(db)


@router.post("/conversations", status_code=201)
def post_conversation(
    body: Optional[CreateConversationRequest] = None,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    title = (body.title if body else None) or "New chat"
    return create_conversation(db, title)


@router.patch("/conversations/{conversation_id}")
def patch_conversation(
    conversation_id: int,
    body: RenameConversationRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        return rename_conversation(db, conversation_id, body.title)
    except ValueError as e:
        status = 404 if "not found" in str(e).lower() else 400
        raise HTTPException(status, str(e)) from e


@router.delete("/conversations/{conversation_id}", status_code=204)
def remove_conversation(conversation_id: int, db: Session = Depends(get_db)) -> None:
    try:
        delete_conversation(db, conversation_id)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e


@router.get("/conversations/{conversation_id}/messages")
def get_messages(conversation_id: int, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    try:
        return get_conversation_messages(db, conversation_id)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e


@router.post(
    "/conversations/{conversation_id}/messages/{message_id}/edit",
    response_model=ChatResponse,
)
def post_edit_message(
    conversation_id: int,
    message_id: int,
    body: EditMessageRequest,
    db: Session = Depends(get_db),
) -> ChatResponse:
    try:
        result = edit_message(
            db,
            conversation_id,
            message_id,
            body.content,
            fork=body.fork,
            page_context=body.page_context,
        )
    except ValueError as e:
        status = 404 if "not found" in str(e).lower() else 400
        raise HTTPException(status, str(e)) from e
    except Exception as e:
        raise HTTPException(502, f"Advisor error: {e}") from e
    return ChatResponse(**result)


@router.get("/history")
def get_history(db: Session = Depends(get_db)) -> list[dict[str, str]]:
    """Legacy: messages from the most recently updated conversation."""
    convs = list_conversations(db)
    if not convs:
        return []
    return [
        {"role": m["role"], "content": m["content"]}
        for m in get_conversation_messages(db, convs[0]["id"])
        if m["role"] in ("user", "assistant")
    ]


@router.post("/chat", response_model=ChatResponse)
def post_chat(body: ChatRequest, db: Session = Depends(get_db)) -> ChatResponse:
    try:
        result = chat_with_advisor(
            db,
            body.message,
            conversation_id=body.conversation_id,
            page_context=body.page_context,
        )
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    except Exception as e:
        raise HTTPException(502, f"Advisor error: {e}") from e
    return ChatResponse(**result)


@router.get("/insights")
def get_insights(db: Session = Depends(get_db)) -> dict[str, list[str]]:
    return {"insights": sync_insights(db)}


@router.post("/actions/propose")
def post_propose(body: ProposeActionRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    return propose_action(db, body.tool_name, body.args)


@router.post("/actions/{action_id}/approve")
def post_approve(
    action_id: int, body: ApproveActionRequest, db: Session = Depends(get_db)
) -> dict[str, Any]:
    try:
        return approve_action(db, action_id, body.approved)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
