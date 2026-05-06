import asyncio
import json
import tiktoken
from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState
from openai import APIConnectionError, APITimeoutError, RateLimitError
from sqlalchemy.ext.asyncio import AsyncSession
from app.core import config
from app.account.auth import verify_token
from app.core.database import AsyncSessionLocal
from app.account.models import get_user_profile
from app.core.limiter import connection_limiter, message_rate_limiter, redis_client
from app.core.logger import logger
from openai import AsyncOpenAI
from app.chat.schemas import ChatResponse
from app.store.services import search_products_in_db, get_featured_products
from app.core.mcp import mcp_server

openai_client = AsyncOpenAI(
    api_key=config.OPENAI_API_KEY,
    timeout=config.OPENAI_TIMEOUT_SECONDS,
)

async def get_openai_tools():
    mcp_tools = await mcp_server.list_tools()
    openai_tools = []
    for tool in mcp_tools:
        openai_tools.append({
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.inputSchema,
            }
        })
    return openai_tools

SYSTEM_PROMPT = (
    "You are a helpful, friendly shopping assistant for Dealnux — an e-commerce platform. "
    "When a user asks about products, always use the search_products tool to find results from the database. "
    "Never make up or guess product names, prices, or availability. "
    "Keep replies concise. "
    "IMPORTANT: When you reply to the user (not making a tool call), you MUST return a valid JSON object with exactly two keys: "
    "\"reply_text\" (your message string) and \"suggested_replies\" (a list of 2-3 short strings for quick reply buttons)."
)


def trim_history(history: list[dict], max_turns: int) -> list[dict]:
    try:
        encoding = tiktoken.encoding_for_model("gpt-4o-mini")

        max_tokens = 8000 
        
        current_tokens = 0
        trimmed = []
        for msg in reversed(history):
            content = msg.get("content") or ""
            
            if len(content) > 15000:
                content = content[:15000] + "... [truncated]"
                msg["content"] = content

            if msg.get("tool_calls"):
                content += json.dumps(msg.get("tool_calls"))
            
            tokens = len(encoding.encode(content)) + 4
            if current_tokens + tokens > max_tokens:
                break
            trimmed.insert(0, msg)
            current_tokens += tokens
            
        while trimmed and trimmed[0].get("role") != "user":
            trimmed.pop(0)
            
        return trimmed
    except Exception as exc:
        logger.warning("Tiktoken trimming failed, falling back to turn trimming", extra={"error": str(exc)})
        max_entries = max_turns * 2
        if len(history) <= max_entries:
            return history
        sliced = history[-max_entries:]
        while sliced and sliced[0].get("role") != "user":
            sliced.pop(0)
        return sliced


def _parse_incoming_message(raw: str) -> str:
    try:
        msg_data = json.loads(raw)
        if isinstance(msg_data, dict):
            return str(msg_data.get("message", raw)).strip()
    except json.JSONDecodeError:
        pass
    return str(raw).strip()


async def _get_personalized_prompt(user_id: int) -> tuple[str, str | None]:
    user_display_name = None
    try:
        async with AsyncSessionLocal() as db_session:
            user = await get_user_profile(db_session, user_id)
            if user:
                if user.name and user.name.strip():
                    user_display_name = user.name.strip()
                elif user.email and user.email.strip():
                    user_display_name = user.email.split("@")[0].strip()
                logger.info(
                    "User profile fetched",
                    extra={"user_id": user_id, "user_name": user_display_name},
                )
    except Exception as exc:
        logger.error(
            "Could not fetch user profile",
            extra={"user_id": user_id, "error_type": type(exc).__name__, "error": str(exc)},
        )

    if user_display_name:
        return (
            f"{SYSTEM_PROMPT} "
            f"The user's name is {user_display_name}. "
            f"Address them by name naturally when appropriate."
        ), user_display_name
    return SYSTEM_PROMPT, None


async def handle_chat_websocket(websocket: WebSocket, token: str | None) -> None:
    try:
        origin = websocket.headers.get("origin")
        if origin and "*" not in config.CORS_ALLOWED_ORIGINS and origin not in config.CORS_ALLOWED_ORIGINS:
            await websocket.close(code=1008, reason="Forbidden Origin")
            return

        await websocket.accept()

        if not token:
            try:
                auth_raw = await asyncio.wait_for(websocket.receive_text(), timeout=30)
            except asyncio.TimeoutError:
                await websocket.close(code=1008, reason="Authentication timeout.")
                return

            try:
                auth_data = json.loads(auth_raw)
                if isinstance(auth_data, dict):
                    token = auth_data.get("token", "")
                else:
                    token = str(auth_raw).strip()
            except json.JSONDecodeError:
                token = auth_raw.strip()

        user_id: int | None = None
        connection_acquired = False

        try:
            user_id = verify_token(token)
        except ValueError as exc:
            await websocket.close(code=1008, reason=str(exc))
            logger.warning("WebSocket auth failed", extra={"reason": str(exc)})
            return

        allowed = await connection_limiter.acquire(user_id)
        if not allowed:
            await websocket.close(
                code=1008,
                reason="Too many active connections. Please close other chat sessions.",
            )
            logger.warning("Connection limit exceeded", extra={"user_id": user_id})
            return
        connection_acquired = True

        personalized_system_prompt, user_display_name = await _get_personalized_prompt(user_id)
        logger.info(
            "WebSocket connected",
            extra={"user_id": user_id, "user_name": user_display_name or "unknown"},
        )

        history_key = f"chat_hist:{user_id}"
        history_data = await redis_client.get(history_key)
        if history_data:
            conversation_history = json.loads(history_data)
        else:
            conversation_history = []
            
            welcome_msg = "Hi! I found some price drops on items similar to your recent searches."
            try:
                async with AsyncSessionLocal() as db_session:
                    initial_products = await get_featured_products(db_session, limit=5)
            except Exception as exc:
                logger.error("Failed to fetch initial products", extra={"user_id": user_id, "error": str(exc)})
                initial_products = []
                
            initial_response = ChatResponse(
                reply_text=welcome_msg,
                products=initial_products,
                suggested_replies=["Show me running shoes under $100", "Compare Prices"]
            )
            conversation_history.append({
                "role": "assistant", 
                "content": welcome_msg,
                "metadata": {
                    "suggested_replies": initial_response.suggested_replies
                }
            })
            await redis_client.set(history_key, json.dumps(conversation_history), ex=86400)
            await websocket.send_text(initial_response.model_dump_json())

        while True:
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=300)
            except asyncio.TimeoutError:
                await websocket.close(code=1001, reason="Session timed out due to inactivity.")
                break

            if not await message_rate_limiter.is_allowed(user_id):
                await websocket.send_text(
                    ChatResponse(
                        reply_text="You're sending messages too quickly. Please slow down.",
                        products=[],
                        suggested_replies=[]
                    ).model_dump_json()
                )
                continue

            message = _parse_incoming_message(raw)
            if not message:
                continue

            if len(message) > config.WS_MAX_MESSAGE_LENGTH:
                await websocket.send_text(
                    ChatResponse(
                        reply_text=(
                            f"Your message is too long. "
                            f"Please keep it under {config.WS_MAX_MESSAGE_LENGTH} characters."
                        ),
                        products=[],
                        suggested_replies=[]
                    ).model_dump_json()
                )
                continue

            logger.info("Message received", extra={"user_id": user_id, "length": len(message)})

            conversation_history.append({"role": "user", "content": message})
            conversation_history = trim_history(conversation_history, config.WS_MAX_HISTORY_TURNS)
            await redis_client.set(history_key, json.dumps(conversation_history), ex=86400)

            try:
                openai_messages = []
                for msg in conversation_history:
                    clean_msg = {k: v for k, v in msg.items() if k != "metadata"}
                    openai_messages.append(clean_msg)

                response = await openai_client.chat.completions.create(
                    model=config.OPENAI_MODEL_CHAT,
                    messages=[
                        {"role": "system", "content": personalized_system_prompt},
                        *openai_messages,
                    ],
                    tools=await get_openai_tools(),
                    tool_choice="auto",
                    parallel_tool_calls=False,
                    temperature=0.4,
                )
            except APITimeoutError:
                logger.error("OpenAI timeout", extra={"user_id": user_id})
                await websocket.send_text(
                    ChatResponse(
                        reply_text="The assistant is taking too long to respond. Please try again.",
                        products=[],
                        suggested_replies=[]
                    ).model_dump_json()
                )
                continue
            except RateLimitError:
                logger.error("OpenAI rate limit hit", extra={"user_id": user_id})
                await websocket.send_text(
                    ChatResponse(
                        reply_text="The assistant is busy right now. Please try again in a moment.",
                        products=[],
                        suggested_replies=[]
                    ).model_dump_json()
                )
                continue
            except APIConnectionError:
                logger.error("OpenAI connection error", extra={"user_id": user_id})
                await websocket.send_text(
                    ChatResponse(
                        reply_text="Could not reach the assistant service. Please check your connection.",
                        products=[],
                        suggested_replies=[]
                    ).model_dump_json()
                )
                continue
            except Exception as exc:
                logger.error("OpenAI unexpected error", extra={"user_id": user_id, "error": str(exc)})
                await websocket.send_text(
                    ChatResponse(
                        reply_text="An unexpected error occurred. Please try asking in a different way.",
                        products=[],
                        suggested_replies=[]
                    ).model_dump_json()
                )
                continue

            response_message = response.choices[0].message
            reply_text = ""
            suggested_replies = []
            found_products = []

            if response_message.tool_calls:
                for tool_call in response_message.tool_calls:
                    tool_name = tool_call.function.name
                    try:
                        args = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError:
                        args = {}

                    logger.info("Tool call initiated", extra={"user_id": user_id, "tool": tool_name})

                    try:
                        tool_results = await mcp_server.call_tool(tool_name, args)
                        tool_output = "\n".join([r.text for r in tool_results if hasattr(r, 'text')])
                        
                        if tool_name in ["search_products", "get_featured_products"]:
                            try:
                                found_products = json.loads(tool_output)
                            except json.JSONDecodeError as e:
                                logger.error("Failed to parse tool output as JSON", extra={"user_id": user_id, "error": str(e), "output": tool_output[:100]})
                                found_products = []

                    except Exception as exc:
                        logger.error("Tool execution error", extra={"user_id": user_id, "tool": tool_name, "error": str(exc)})
                        tool_output = f"Error: {str(exc)}"
                        found_products = []

                    conversation_history.append(
                        {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": tool_call.id,
                                    "type": "function",
                                    "function": {
                                        "name": tool_name,
                                        "arguments": tool_call.function.arguments,
                                    },
                                }
                            ],
                        }
                    )
                    conversation_history.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": tool_output,
                        }
                    )

                    try:
                        openai_messages = []
                        for msg in conversation_history:
                            clean_msg = {k: v for k, v in msg.items() if k != "metadata"}
                            openai_messages.append(clean_msg)

                        followup = await openai_client.chat.completions.create(
                            model=config.OPENAI_MODEL_CHAT,
                            messages=[
                                {"role": "system", "content": personalized_system_prompt},
                                *openai_messages,
                            ],
                            response_format={"type": "json_object"},
                            temperature=0.4,
                        )
                        raw_content = followup.choices[0].message.content or "{}"
                        data = json.loads(raw_content)
                        reply_text = data.get("reply_text", "")
                        suggested_replies = data.get("suggested_replies", [])
                        
                        conversation_history.append({
                            "role": "assistant", 
                            "content": reply_text, 
                            "metadata": {"suggested_replies": suggested_replies}
                        })
                        
                    except Exception as exc:
                        logger.error("OpenAI follow-up error", extra={"user_id": user_id, "error": str(exc)})
                        reply_text = f"I found some options for you." if found_products else "I couldn't find exactly what you were looking for."
                        suggested_replies = ["Show more", "Compare Prices"]
                        conversation_history.append({
                            "role": "assistant", 
                            "content": reply_text,
                        })
            else:
                try:
                    raw_content = response_message.content or "{}"
                    if raw_content.strip().startswith("{"):
                        data = json.loads(raw_content)
                        reply_text = data.get("reply_text", "")
                        suggested_replies = data.get("suggested_replies", [])
                    else:
                        reply_text = raw_content
                        suggested_replies = []

                    conversation_history.append({
                        "role": "assistant", 
                        "content": reply_text, 
                        "metadata": {"suggested_replies": suggested_replies}
                    })
                except Exception as exc:
                    logger.warning("Failed to parse assistant JSON", extra={"user_id": user_id, "error": str(exc)})
                    reply_text = response_message.content or ""
                    suggested_replies = []
                    conversation_history.append({
                        "role": "assistant", 
                        "content": reply_text, 
                        "metadata": {"suggested_replies": []}
                    })
                found_products = []

            await redis_client.set(history_key, json.dumps(conversation_history), ex=86400)

            await websocket.send_text(
                ChatResponse(reply_text=reply_text, products=found_products, suggested_replies=suggested_replies).model_dump_json()
            )
            
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected cleanly", extra={"user_id": user_id if 'user_id' in locals() else None})
    except Exception as exc:
        logger.error("Fatal websocket error", extra={"error": str(exc)}, exc_info=True)
        if websocket.client_state != WebSocketState.DISCONNECTED:
            await websocket.close(code=1011)
    finally:
        if 'connection_acquired' in locals() and connection_acquired and 'user_id' in locals() and user_id is not None:
            await connection_limiter.release(user_id)
