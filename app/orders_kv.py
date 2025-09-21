# app/orders_kv.py

from typing import Dict, Any, List
import secrets, time
from eth_account import Account
from uagents import Context

ORDERS_KEY = "orders_v1"  # maps: order_id -> order dict

def _load(ctx: Context) -> Dict[str, Any]:
    return ctx.storage.get(ORDERS_KEY) or {}

def _save(ctx: Context, orders: Dict[str, Any]) -> None:
    ctx.storage.set(ORDERS_KEY, orders)

def create_order(ctx: Context, symbol: str, token_address: str, recipient: str, slippage_bps: int) -> Dict[str, Any]:
    priv = "0x" + secrets.token_hex(32)
    acct = Account.from_key(priv)
    oid  = secrets.token_hex(12)
    now  = int(time.time())

    order = {
        "id": oid,
        "symbol": symbol,
        "token_address": token_address,
        "recipient": recipient,
        "slippage_bps": int(slippage_bps),
        "recv_priv": priv,           # 🔒 stored locally in the agent’s storage JSON
        "recv_addr": acct.address,
        "status": "pending",         # pending | complete | error
        "created_at": now,
        "last_error": None,
    }
    orders = _load(ctx)
    orders[oid] = order
    _save(ctx, orders)
    return order

def list_pending(ctx: Context) -> List[Dict[str, Any]]:
    return [o for o in _load(ctx).values() if o.get("status") == "pending"]

def mark_complete(ctx: Context, order_id: str) -> None:
    orders = _load(ctx)
    if order_id in orders:
        orders[order_id]["status"] = "complete"
        _save(ctx, orders)

def mark_error(ctx: Context, order_id: str, err: str) -> None:
    orders = _load(ctx)
    if order_id in orders:
        orders[order_id]["status"] = "error"
        orders[order_id]["last_error"] = err
        _save(ctx, orders)

def get_order(ctx: Context, order_id: str) -> Dict[str, Any] | None:
    return _load(ctx).get(order_id)
