from mcp.server import Server
from mcp.types import Tool, TextContent
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import AsyncSessionLocal
from app.store.services import search_products_in_db, get_featured_products
import json

mcp_server = Server("Dealnux Chatbot")

@mcp_server.list_tools()
async def handle_list_tools() -> list[Tool]:
    """List available tools for the Dealnux shopping assistant."""
    return [
        Tool(
            name="search_products",
            description="Search the Dealnux product database based on user requirements.",
            inputSchema={
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "Product name or type"},
                    "max_price": {"type": "number", "description": "Maximum price"},
                    "min_price": {"type": "number", "description": "Minimum price"},
                    "condition": {
                        "type": "string",
                        "enum": ["NEW", "USED", "REFURBISHED", "OPEN_BOX"],
                        "description": "Product condition",
                    },
                    "free_shipping": {"type": "boolean", "description": "Free shipping filter"},
                },
                "required": ["keyword"],
            },
        ),
        Tool(
            name="get_featured_products",
            description="Get a list of currently featured or newly added products.",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 5, "description": "Number of products to return"}
                },
            },
        ),
    ]

@mcp_server.call_tool()
async def handle_call_tool(name: str, arguments: dict | None) -> list[TextContent]:
    """Handle tool execution requests from the AI."""
    if not arguments:
        arguments = {}

    async with AsyncSessionLocal() as db:
        if name == "search_products":
            keyword = arguments.get("keyword", "")
            max_price = arguments.get("max_price")
            min_price = arguments.get("min_price")
            condition = arguments.get("condition")
            free_shipping = arguments.get("free_shipping")

            products = await search_products_in_db(
                db,
                keyword=keyword,
                max_price=max_price,
                min_price=min_price,
                condition=condition,
                free_shipping=free_shipping,
            )
            return [TextContent(type="text", text=json.dumps([p.model_dump() for p in products], default=str))]

        elif name == "get_featured_products":
            limit = arguments.get("limit", 5)
            products = await get_featured_products(db, limit=limit)
            return [TextContent(type="text", text=json.dumps([p.model_dump() for p in products], default=str))]

        else:
            raise ValueError(f"Unknown tool: {name}")
