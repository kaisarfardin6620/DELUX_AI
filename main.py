import json
import asyncio
from contextlib import asynccontextmanager
from typing import List, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from openai import AsyncOpenAI, APITimeoutError, APIConnectionError, RateLimitError
import config
from database import get_db, AsyncSessionLocal, Product, ProductListing, Platform
from auth import verify_token
from limiter import connection_limiter, message_rate_limiter, redis_client
from logger import logger

openai_client = AsyncOpenAI(
    api_key=config.OPENAI_API_KEY,
    timeout=config.OPENAI_TIMEOUT_SECONDS,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Chatbot service starting up", extra={"env": "production"})
    yield
    await redis_client.aclose()
    logger.info("Chatbot service shutting down")


app = FastAPI(
    title="Dealnux Chatbot API",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception", extra={"path": request.url.path, "error": str(exc)})
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "ok", "db": "connected"}
    except Exception as e:
        logger.error("Health check DB failure", extra={"error": str(e)})
        raise HTTPException(status_code=503, detail="Database unavailable")


class ProductCard(BaseModel):
    id: int
    title: str
    image_url: Optional[str]
    price: Optional[float]
    original_price: Optional[float]
    discount_percentage: Optional[float]
    platform_name: str
    external_url: Optional[str]
    condition: Optional[str]
    currency: Optional[str]
    free_shipping: Optional[bool]


class ChatResponse(BaseModel):
    reply_text: str
    products: List[ProductCard] =[]


def build_image_url(relative_path: str | None) -> str | None:
    if not relative_path:
        return None
    return config.DJANGO_MEDIA_URL.rstrip("/") + "/" + relative_path.lstrip("/")


def trim_history(history: list[dict], max_turns: int) -> list[dict]:
    max_entries = max_turns * 2
    if len(history) > max_entries:
        return history[-max_entries:]
    return history

async def search_products_in_db(
    db: AsyncSession,
    keyword: str,
    max_price: float = None,
    min_price: float = None,
    condition: str = None,
    free_shipping: bool = None,
) -> List[ProductCard]:
    query = (
        select(Product, ProductListing, Platform)
        .join(ProductListing, Product.id == ProductListing.product_id)
        .join(Platform, ProductListing.platform_id == Platform.id)
        .where(ProductListing.is_available == True)
        .where(ProductListing.quantity > 0)
    )

    if keyword:
        query = query.where(Product.title.ilike(f"%{keyword}%"))
    if max_price is not None:
        query = query.where(ProductListing.price <= max_price)
    if min_price is not None:
        query = query.where(ProductListing.price >= min_price)
    if condition:
        query = query.where(ProductListing.condition == condition.upper())
    if free_shipping is True:
        query = query.where(ProductListing.free_shipping == True)

    query = query.order_by(ProductListing.price.asc()).limit(5)

    result = await db.execute(query)
    rows = result.all()

    products =[]
    for prod, listing, platform in rows:
        products.append(ProductCard(
            id=prod.id,
            title=prod.title,
            image_url=build_image_url(prod.main_image),
            price=float(listing.price) if listing.price is not None else None,
            original_price=float(listing.original_price) if listing.original_price is not None else None,
            discount_percentage=float(listing.discount_percentage) if listing.discount_percentage is not None else None,
            platform_name=platform.name,
            external_url=listing.external_url,
            condition=listing.condition,
            currency=listing.currency,
            free_shipping=listing.free_shipping,
        ))
    return products


TOOLS =[
    {
        "type": "function",
        "function": {
            "name": "search_products",
            "description": "Search the Dealnux product database based on user requirements.",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "Product name or type (e.g. 'smartphone', 'running shoes')",
                    },
                    "max_price": {
                        "type": "number",
                        "description": "Maximum price the user wants to pay",
                    },
                    "min_price": {
                        "type": "number",
                        "description": "Minimum price filter",
                    },
                    "condition": {
                        "type": "string",
                        "enum":["NEW", "USED", "REFURBISHED", "OPEN_BOX"],
                        "description": "Product condition filter",
                    },
                    "free_shipping": {
                        "type": "boolean",
                        "description": "Set to true if user wants only free-shipping products",
                    },
                },
                "required": ["keyword"],
            },
        },
    }
]

SYSTEM_PROMPT = (
    "You are a helpful, friendly shopping assistant for Dealnux — an e-commerce platform. "
    "When a user asks about products, always use the search_products tool to find results from the database. "
    "Never make up or guess product names, prices, or availability — only show what the tool returns. "
    "Keep replies concise. If no products are found, suggest rephrasing or trying a broader keyword. "
    "You can understand follow-up questions that refer to previous context in the conversation."
)


@app.websocket("/api/chat")
async def websocket_chat(
    websocket: WebSocket,
    token: str = Query(default=None),
):
    await websocket.accept()

    # If token not in query params, fall back to first message
    if not token:
        try:
            auth_raw = await asyncio.wait_for(websocket.receive_text(), timeout=15)
        except asyncio.TimeoutError:
            await websocket.close(code=1008, reason="Authentication timeout.")
            return
        try:
            auth_data = json.loads(auth_raw)
            token = auth_data.get("token", "")
        except (json.JSONDecodeError, AttributeError):
            token = auth_raw.strip()

    try:
        user_id = verify_token(token)
    except ValueError as e:
        await websocket.close(code=1008, reason=str(e))
        logger.warning("WebSocket auth failed", extra={"reason": str(e)})
        return

    allowed = await connection_limiter.acquire(user_id)
    if not allowed:
        await websocket.close(
            code=1008,
            reason="Too many active connections. Please close other chat sessions.",
        )
        logger.warning("Connection limit exceeded", extra={"user_id": user_id})
        return

    logger.info("WebSocket connected", extra={"user_id": user_id})

    conversation_history: list[dict] =[]

    try:
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
                    ).model_dump_json()
                )
                continue

            try:
                msg_data = json.loads(raw)
                message = msg_data.get("message", raw)
            except json.JSONDecodeError:
                message = raw

            message = str(message).strip()

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
                    ).model_dump_json()
                )
                continue

            logger.info("Message received", extra={"user_id": user_id, "length": len(message)})

            conversation_history.append({"role": "user", "content": message})
            conversation_history = trim_history(
                conversation_history, config.WS_MAX_HISTORY_TURNS
            )

            try:
                response = await openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        *conversation_history,
                    ],
                    tools=TOOLS,
                    tool_choice="auto",
                    temperature=0.4,
                )
            except APITimeoutError:
                logger.error("OpenAI timeout", extra={"user_id": user_id})
                await websocket.send_text(
                    ChatResponse(
                        reply_text="The assistant is taking too long to respond. Please try again.",
                        products=[],
                    ).model_dump_json()
                )
                continue
            except RateLimitError:
                logger.error("OpenAI rate limit hit", extra={"user_id": user_id})
                await websocket.send_text(
                    ChatResponse(
                        reply_text="The assistant is busy right now. Please try again in a moment.",
                        products=[],
                    ).model_dump_json()
                )
                continue
            except APIConnectionError:
                logger.error("OpenAI connection error", extra={"user_id": user_id})
                await websocket.send_text(
                    ChatResponse(
                        reply_text="Could not reach the assistant service. Please check your connection.",
                        products=[],
                    ).model_dump_json()
                )
                continue

            response_message = response.choices[0].message

            if response_message.tool_calls:
                tool_call = response_message.tool_calls[0]

                try:
                    args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    args = {}

                keyword       = str(args.get("keyword", "")).strip()
                max_price     = args.get("max_price")
                min_price     = args.get("min_price")
                condition     = args.get("condition")
                free_shipping = args.get("free_shipping")

                try:
                    async with AsyncSessionLocal() as db_session:
                        found_products = await search_products_in_db(
                            db_session,
                            keyword=keyword,
                            max_price=max_price,
                            min_price=min_price,
                            condition=condition,
                            free_shipping=free_shipping,
                        )
                except Exception as e:
                    logger.error("DB search error", extra={"user_id": user_id, "error": str(e)})
                    await websocket.send_text(
                        ChatResponse(
                            reply_text="There was a problem searching the database. Please try again.",
                            products=[],
                        ).model_dump_json()
                    )
                    continue

                logger.info(
                    "Product search completed",
                    extra={"user_id": user_id, "keyword": keyword, "results": len(found_products)},
                )

                conversation_history.append({
                    "role": "assistant",
                    "content": None,
                    "tool_calls":[
                        {
                            "id": tool_call.id,
                            "type": "function",
                            "function": {
                                "name": tool_call.function.name,
                                "arguments": tool_call.function.arguments,
                            },
                        }
                    ],
                })
                conversation_history.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(
                        [p.model_dump() for p in found_products], default=str
                    ),
                })

                try:
                    followup = await openai_client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[
                            {"role": "system", "content": SYSTEM_PROMPT},
                            *conversation_history,
                        ],
                        temperature=0.4,
                    )
                    reply_text = followup.choices[0].message.content or ""
                except Exception as e:
                    logger.error("OpenAI follow-up error", extra={"user_id": user_id, "error": str(e)})
                    if found_products:
                        reply_text = f"Here are some {keyword} options I found for you:"
                    else:
                        reply_text = (
                            f"Sorry, I couldn't find any '{keyword}' matching your criteria. "
                            "Try a broader keyword or adjust your filters."
                        )

            else:
                reply_text     = response_message.content or ""
                found_products =[]

            conversation_history.append({"role": "assistant", "content": reply_text})

            await websocket.send_text(
                ChatResponse(reply_text=reply_text, products=found_products).model_dump_json()
            )

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected cleanly", extra={"user_id": user_id})
    except Exception as e:
        logger.error("Unexpected WebSocket error", extra={"user_id": user_id, "error": str(e)})
    finally:
        await connection_limiter.release(user_id)