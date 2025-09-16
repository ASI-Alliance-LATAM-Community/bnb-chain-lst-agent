import requests
from uagents import Agent, Context, Protocol
from typing import List, Dict, Any
from datetime import datetime, timezone
from uuid import uuid4
from uagents_core.contrib.protocols.chat import (
    chat_protocol_spec,
    ChatMessage,
    ChatAcknowledgement,
    TextContent,
    StartSessionContent,
)
import os
from dotenv import load_dotenv
import json

load_dotenv()

# ASI1 Config

ASI1_API_KEY = os.getenv("ASI1_API_KEY")
ASI1_BASE_URL = "https://api.asi1.ai/v1"
ASI1_HEADERS = {
    "Authorization": f"Bearer {ASI1_API_KEY}",
    "Content-Type": "application/json",
}

# BNB Chain Config

BSC_RPC_URL = os.getenv("BSC_RPC_URL")

if not ASI1_API_KEY:
    raise RuntimeError("ASI1_API_KEY not set. Add it to your environment or .env")
if not BSC_RPC_URL:
    raise RuntimeError("BSC_RPC_URL not set. Add it to your environment or .env")

# LST Tokens Config

LST_REGISTRY_BSC: List[Dict[str, Any]] = [
    {
        "symbol": "BNBx",
        "name": "Stader BNBx",
        "address": "0x1bdd3cf7f79cfb8edbb955f20ad99211551ba275",
        "project": "Stader",
        "coingecko_id": "stader-bnbx",
        "sources": [
            "https://binance.docs.staderlabs.com/bnbx-faqs/tokens-and-contract",
            "https://bscscan.com/token/0x1bdd3cf7f79cfb8edbb955f20ad99211551ba275",
        ],
    },
    {
        "symbol": "ANKRBNB",
        "name": "Ankr Staked BNB",
        "address": "0x52f24a5e03aee338da5fd9df68d2b6fae1178827",
        "project": "Ankr",
        "coingecko_id": "ankr-staked-bnb",
        "sources": [
            "https://www.ankr.com/docs/liquid-staking/bnb/overview/",
            "https://www.coingecko.com/en/coins/ankr-staked-bnb",
            "https://bscscan.com/token/0x52f24a5e03aee338da5fd9df68d2b6fae1178827",
        ],
    },
    {
        "symbol": "STKBNB",
        "name": "pSTAKE Staked BNB",
        "address": "0xc2e9d07f66a89c44062459a47a0d2dc038e4fb16",
        "project": "pSTAKE",
        "coingecko_id": "pstake-staked-bnb",
        "sources": [
            "https://www.coingecko.com/en/coins/pstake-staked-bnb",
            "https://bscscan.com/token/0xc2e9d07f66a89c44062459a47a0d2dc038e4fb16",
        ],
    }
]

# COINGECKO / GECKOTERMINAL / PANCAKESWAP INFO HELPERS

CG_BASE = "https://api.coingecko.com/api/v3"
GT_BASE = "https://api.geckoterminal.com/api/v2"
BINANCE_BASE = "https://api.binance.com"
PANCAKE_INFO_BASE = "https://api.pancakeswap.info/api/v2"
WBNB_BSC = "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c".lower()
DEFAULT_HEADERS = {
    "Accept": "application/json",
    "User-Agent": "bnb-chain-lst-agent/1.0 (+https://example.com)"
}

# Helpers to fetch prices

def fetch_bnb_price() -> Dict[str, Any]:
    """
    Returns {"bnb_usd": float, "source": str} without needing an API key.
    Tries CoinGecko (by id) -> GeckoTerminal (WBNB) -> PancakeSwap Info.
    """

    try:
        r = requests.get(
            f"{CG_BASE}/simple/price",
            params={"ids": "binancecoin", "vs_currencies": "usd", "precision": "full"},
            headers=DEFAULT_HEADERS,
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        px = data.get("binancecoin", {}).get("usd")
        if px is not None:
            return {"bnb_usd": float(px), "source": "coingecko_id"}
    except Exception:
        pass


    try:
        r = requests.get(
            f"{GT_BASE}/simple/networks/bsc/token_price/{WBNB_BSC}",
            headers=DEFAULT_HEADERS,
            timeout=15,
        )
        r.raise_for_status()
        gt = r.json()
        px_map = gt.get("data", {}).get("attributes", {}).get("token_prices", {})
        px = px_map.get(WBNB_BSC)
        if px is not None:
            return {"bnb_usd": float(px), "source": "geckoterminal"}
    except Exception:
        pass


    try:
        r = requests.get(
            f"{PANCAKE_INFO_BASE}/tokens/{WBNB_BSC}",
            headers=DEFAULT_HEADERS,
            timeout=15,
        )
        r.raise_for_status()
        info = r.json()
        px = info.get("data", {}).get("price")
        if px is not None:
            return {"bnb_usd": float(px), "source": "pancakeswap_info"}
    except Exception as e:
        raise

    raise RuntimeError("Unable to fetch BNB/USD from public sources (CG/GT/Pancake).")

def _cg_simple_price_by_ids(ids: List[str]) -> Dict[str, Dict[str, Any]]:
    """
    Price USD + 24h change by CoinGecko ID (not contract). No API key required.
    Returns { coingecko_id: {"usd": float, "usd_24h_change": float, "last_updated_at": ts} }
    """
    if not ids:
        return {}
    r = requests.get(
        f"{CG_BASE}/simple/price",
        params={
            "ids": ",".join(ids),
            "vs_currencies": "usd",
            "include_24hr_change": "true",
            "precision": "full",
        },
        timeout=20,
        headers={"Accept": "application/json"},
    )
    r.raise_for_status()
    data = r.json()
    now_ts = int(datetime.now(tz=timezone.utc).timestamp())
    out: Dict[str, Dict[str, Any]] = {}
    for cid, v in data.items():
        out[cid] = {
            "usd": float(v.get("usd")) if v.get("usd") is not None else None,
            "usd_24h_change": float(v.get("usd_24h_change")) if v.get("usd_24h_change") is not None else None,
            "last_updated_at": now_ts,
            "_source": "coingecko_ids"
        }
    return out

def _gt_simple_by_addresses(addresses: List[str]) -> Dict[str, Dict[str, Any]]:
    """
    GeckoTerminal: Prices by contract on BSC. No key required.
    Returns { address_lower: {"usd": float, "usd_24h_change": None, "last_updated_at": ts} }
    """
    if not addresses:
        return {}
    path_addrs = ",".join([a.lower() for a in addresses])
    r = requests.get(
        f"{GT_BASE}/simple/networks/bsc/token_price/{path_addrs}",
        timeout=20,
        headers={"Accept": "application/json"},
    )
    r.raise_for_status()
    data = r.json()
    prices_map = data.get("data", {}).get("attributes", {}).get("token_prices", {}) or {}
    out: Dict[str, Dict[str, Any]] = {}
    now_ts = int(datetime.now(tz=timezone.utc).timestamp())
    for addr, price_str in prices_map.items():
        try:
            usd = float(price_str)
        except Exception:
            usd = None
        out[addr.lower()] = {
            "usd": usd,
            "usd_24h_change": None,
            "last_updated_at": now_ts,
            "_source": "geckoterminal",
        }
    return out

def fetch_lst_prices_bsc(addresses: List[str], id_map: Dict[str, str]) -> Dict[str, Dict[str, Any]]:
    """
    Mix: first tries CoinGecko IDs (no key) for those that have a coingecko_id,
    and for the rest uses GeckoTerminal by contract.
    – addresses: list of contracts (checksummed or lowercase)
    – id_map: { address_lower: coingecko_id }
    Returns a dict indexed by address_lower with fields "usd", "usd_24h_change", "last_updated_at".
    """

    ids = sorted(set([cid for cid in id_map.values() if cid]))
    cg_by_id = _cg_simple_price_by_ids(ids) if ids else {}


    need_addr = [a.lower() for a in addresses if not id_map.get(a.lower())]
    gt_by_addr = _gt_simple_by_addresses(need_addr) if need_addr else {}


    now_ts = int(datetime.now(tz=timezone.utc).timestamp())
    result: Dict[str, Dict[str, Any]] = {}
    for addr in [a.lower() for a in addresses]:
        cid = id_map.get(addr)
        if cid and cid in cg_by_id:
            result[addr] = {
                "usd": cg_by_id[cid]["usd"],
                "usd_24h_change": cg_by_id[cid]["usd_24h_change"],
                "last_updated_at": cg_by_id[cid]["last_updated_at"],
            }
        elif addr in gt_by_addr:
            result[addr] = gt_by_addr[addr]
        else:
            result[addr] = {"usd": None, "usd_24h_change": None, "last_updated_at": now_ts}
    return result

def list_lst_tokens() -> List[Dict[str, Any]]:
    addrs = [t["address"] for t in LST_REGISTRY_BSC]
    id_map = {t["address"].lower(): t.get("coingecko_id") for t in LST_REGISTRY_BSC}
    prices = fetch_lst_prices_bsc(addrs, id_map)
    bnb_info = fetch_bnb_price()
    bnb_usd = bnb_info["bnb_usd"]

    now_iso = datetime.now(timezone.utc).isoformat()
    enriched: List[Dict[str, Any]] = []
    for t in LST_REGISTRY_BSC:
        addr = t["address"].lower()
        p = prices.get(addr, {})
        price_usd = float(p.get("usd")) if p.get("usd") is not None else None
        change_24h = float(p.get("usd_24h_change")) if p.get("usd_24h_change") is not None else None
        last_upd = p.get("last_updated_at")
        price_bnb = (price_usd / bnb_usd) if (price_usd is not None and bnb_usd) else None

        enriched.append(
            {
                "symbol": t["symbol"],
                "name": t["name"],
                "address": t["address"],
                "project": t["project"],
                "price_usd": price_usd,
                "price_bnb": price_bnb,
                "peg_ratio": price_bnb,
                "change_24h_pct": change_24h,
                "sources": t.get("sources", []),
                "last_updated": datetime.fromtimestamp(last_upd, tz=timezone.utc).isoformat() if last_upd else now_iso,
            }
        )
    return enriched

tools = [
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
    }
]

def dispatch_tool(func_name: str, _args: Dict[str, Any], ctx: Context) -> Dict[str, Any]:
    try:
        if func_name == "list_lst_tokens":
            data = list_lst_tokens()
            return {"ok": True, "tokens": data}
        else:
            return {"ok": False, "error": f"Unsupported tool: {func_name}"}
    except Exception as e:
        ctx.logger.error(f"Tool {func_name} failed: {e}")
        return {"ok": False, "error": str(e)}

async def process_query(query: str, ctx: Context) -> str:
    try:
        user_message = {"role": "user", "content": query}
        system_message = {
            "role": "system",
            "content": (
                "You are an AI assistant called BNB-chain-LST-Agent. "
                "You are a BNB-chain liquid staking expert. "
                "When the user asks for LST list or prices, call the function list_lst_tokens. "
                "Here is the list of known LST tokens on BNB chain:\n"
                f"{LST_REGISTRY_BSC}"
            ),
        }
        
        payload = {
            "model": "asi1-mini",
            "messages": [system_message, user_message],
            "tools": tools,
            "tool_choice": "auto",
            "temperature": 0.2,
            "max_tokens": 1024,
        }

        resp = requests.post(
            f"{ASI1_BASE_URL}/chat/completions",
            headers=ASI1_HEADERS,
            json=payload,
            timeout=60,
        )
        resp.raise_for_status()
        response_json = resp.json()
        model_msg = response_json["choices"][0]["message"]

        messages_history = [system_message, user_message, model_msg]

        tool_calls = model_msg.get("tool_calls", []) or []

        for tc in tool_calls:
            func_name = tc["function"]["name"]
            args = json.loads(tc["function"].get("arguments") or "{}")
            tool_result = dispatch_tool(func_name, args, ctx)

            messages_history.append(
                {
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "name": func_name,
                    "content": json.dumps(tool_result),
                }
            )

        final = requests.post(
            f"{ASI1_BASE_URL}/chat/completions",
            headers=ASI1_HEADERS,
            json={
                "model": "asi1-mini",
                "messages": messages_history,
                "temperature": 0.2,
                "max_tokens": 2048,
            },
            timeout=60,
        )
        final.raise_for_status()
        return final.json()["choices"][0]["message"]["content"]

    except Exception as e:
        ctx.logger.error(f"Error processing query: {e}")
        return f"An error occurred: {e}"

# Agent and Protocol Setup

agent = Agent(
    name="bnb-chain-lst-agent", 
    port=8001, 
    mailbox=True
)
chat_proto = Protocol(spec=chat_protocol_spec)

@chat_proto.on_message(model=ChatMessage)
async def handle_chat_message(ctx: Context, sender: str, msg: ChatMessage):
    try:
        ack = ChatAcknowledgement(
            timestamp=datetime.now(timezone.utc), acknowledged_msg_id=msg.msg_id
        )
        await ctx.send(sender, ack)

        for item in msg.content:
            if isinstance(item, StartSessionContent):
                ctx.logger.info(f"Got a start session message from {sender}")
                continue
            elif isinstance(item, TextContent):
                ctx.logger.info(f"Got a message from {sender}: {item.text}")
                response_text = await process_query(item.text, ctx)
                ctx.logger.info(f"Response text: {response_text}")
                response = ChatMessage(
                    timestamp=datetime.now(timezone.utc),
                    msg_id=uuid4(),
                    content=[TextContent(type="text", text=response_text)],
                )
                await ctx.send(sender, response)
            else:
                ctx.logger.info(f"Got unexpected content from {sender}")
    except Exception as e:
        ctx.logger.error(f"Error handling chat message: {str(e)}")
        error_response = ChatMessage(
            timestamp=datetime.now(timezone.utc),
            msg_id=uuid4(),
            content=[TextContent(type="text", text=f"An error occurred: {str(e)}")],
        )
        await ctx.send(sender, error_response)


@chat_proto.on_message(model=ChatAcknowledgement)
async def handle_chat_acknowledgement(
    ctx: Context, sender: str, msg: ChatAcknowledgement
):
    ctx.logger.info(
        f"Received acknowledgement from {sender} for message {msg.acknowledged_msg_id}"
    )
    if msg.metadata:
        ctx.logger.info(f"Metadata: {msg.metadata}")

agent.include(chat_proto)

if __name__ == "__main__":
    agent.run()