from fastapi import APIRouter, Query, WebSocket
from app.chat.services import handle_chat_websocket

router = APIRouter()

@router.websocket("/api/chat")
async def websocket_chat(websocket: WebSocket, token: str = Query(default=None)):
    await handle_chat_websocket(websocket, token)
