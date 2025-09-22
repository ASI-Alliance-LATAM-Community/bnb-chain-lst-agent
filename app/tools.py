from typing import Dict, Any
from uagents import Context

from .prices import list_lst_tokens, get_bnb_info
from .managed_buy import create_managed_buy

tools_schema = [
    {
        "type": "function",
        "function": {
            "name": "list_lst_tokens",
            "description": "Lists all supported LST tokens on BNB Chain with current price and relevant metadata.",
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_bnb_info",
            "description": "Returns current BNB price in USD, 24h change (if available), timestamp, and basic metadata.",
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_managed_buy",
            "description": "Create a managed order with a BNB 'pay' URI and a deposit address. The agent will swap BNB→LST and send tokens to the recipient.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol_or_address": {"type": "string"},
                    "recipient_address": {"type": "string"},
                    "slippage_bps": {"type": "integer"},
                },
                "required": ["symbol_or_address", "recipient_address"],
                "additionalProperties": False,
            },
        },
    },
]


def dispatch_tool(
    func_name: str, _args: Dict[str, Any], ctx: Context
) -> Dict[str, Any]:
    try:
        if func_name == "list_lst_tokens":
            data = list_lst_tokens()
            return {"ok": True, "tokens": data}
        elif func_name == "get_bnb_info":
            data = get_bnb_info()
            return {"ok": True, "bnb": data}
        elif func_name == "create_managed_buy":
            return create_managed_buy(
                ctx,
                _args["symbol_or_address"],
                _args["recipient_address"],
                _args.get("slippage_bps"),
            )
        else:
            return {"ok": False, "error": f"Unsupported tool: {func_name}"}
    except Exception as e:
        ctx.logger.error(f"Tool {func_name} failed: {e}")
        return {"ok": False, "error": str(e)}
