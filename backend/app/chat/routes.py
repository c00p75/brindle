from fastapi import APIRouter, Depends

from app.auth.deps import current_user
from app.auth.models import User
from app.chat.models import ChatRequest, ChatResponse
from app.chat.service import clear_session, process_message

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(body: ChatRequest, user: User = Depends(current_user)) -> ChatResponse:
    reply, session_id, actions = await process_message(
        message=body.message,
        session_id=body.session_id,
        user=user,
    )
    return ChatResponse(reply=reply, session_id=session_id, actions=actions)


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(session_id: str, _: User = Depends(current_user)) -> None:
    clear_session(session_id)
