from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class ChatResponse(BaseModel):
    reply: str
    session_id: str
    actions: list[str] = []


class ChatMessage(BaseModel):
    role: str
    content: str
    tool_calls: list[dict] | None = None
    tool_call_id: str | None = None
    at_ms: int


class ChatSession(BaseModel):
    id: str
    title: str
    created_at_ms: int
    updated_at_ms: int
