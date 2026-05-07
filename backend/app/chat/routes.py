from fastapi import APIRouter, Depends

from app.auth.deps import current_user
from app.auth.models import User
from app.chat.models import ChatMessage, ChatRequest, ChatResponse, ChatSession
from app.chat.service import clear_session, get_history, list_sessions, process_message

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.get("/sessions", response_model=list[ChatSession])
async def sessions(user: User = Depends(current_user)) -> list[ChatSession]:
    return await list_sessions(user.id)


@router.get("/sessions/{session_id}/history", response_model=list[ChatMessage])
async def history(session_id: str, _: User = Depends(current_user)) -> list[ChatMessage]:
    return await get_history(session_id)


@router.post("", response_model=ChatResponse)
async def chat(body: ChatRequest, user: User = Depends(current_user)) -> ChatResponse:
    reply, session_id, actions, entities, steps = await process_message(
        message=body.message,
        session_id=body.session_id,
        user=user,
    )
    return ChatResponse(
        reply=reply,
        session_id=session_id,
        actions=actions,
        entities=entities,
        steps=steps
    )


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(session_id: str, _: User = Depends(current_user)) -> None:
    clear_session(session_id)
