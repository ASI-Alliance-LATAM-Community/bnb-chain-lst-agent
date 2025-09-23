from typing import Dict, Any, List
import secrets, time
from eth_account import Account
from uagents import Context

ORDERS_KEY = "orders_v5"


def _load(ctx: Context) -> Dict[str, Any]:
    return ctx.storage.get(ORDERS_KEY) or {}


def _save(ctx: Context, orders: Dict[str, Any]) -> None:
    ctx.storage.set(ORDERS_KEY, orders)


def create_order(
    ctx: Context, symbol: str, token_address: str, recipient: str, slippage_bps: int
) -> Dict[str, Any]:
    priv = "0x" + secrets.token_hex(32)
    acct = Account.from_key(priv)
    oid = secrets.token_hex(12)
    now = int(time.time())

    order = {
        "id": oid,
        "symbol": symbol,
        "token_address": token_address,
        "recipient": recipient,
        "slippage_bps": int(slippage_bps),
        "recv_priv": priv,
        "recv_addr": acct.address,
        "status": "pending",  # pending | refund_pending | complete | refunded
        "created_at": now,
        "last_error": None,
        "tx_hash": None,
        "delivered_raw": None,
        "notify_agent": None,
        "notified_funded": False,
        "attempts": 0,
    }
    orders = _load(ctx)
    orders[oid] = order
    _save(ctx, orders)
    return order


def list_active(ctx: Context) -> List[Dict[str, Any]]:
    return [
        o
        for o in _load(ctx).values()
        if o.get("status") in ("pending", "refund_pending")
    ]


def mark_complete(
    ctx: Context,
    order_id: str,
    tx_hash: str | None = None,
    delivered_raw: int | None = None,
) -> None:
    orders = _load(ctx)
    if order_id in orders:
        if tx_hash is not None:
            orders[order_id]["tx_hash"] = tx_hash
        if delivered_raw is not None:
            orders[order_id]["delivered_raw"] = delivered_raw
        orders[order_id]["status"] = "complete"
        _save(ctx, orders)
        ctx.logger.info(f"[orders] mark_complete {order_id} tx={tx_hash}")


def mark_refund_pending(ctx: Context, order_id: str, err: str | None = None) -> None:
    orders = _load(ctx)
    if order_id in orders:
        orders[order_id]["status"] = "refund_pending"
        if err:
            orders[order_id]["last_error"] = err
        _save(ctx, orders)
        ctx.logger.warning(f"[orders] refund_pending {order_id}: {err or ''}")


def mark_refunded(ctx: Context, order_id: str, tx_hash: str | None = None) -> None:
    orders = _load(ctx)
    if order_id in orders:
        orders[order_id]["status"] = "refunded"
        if tx_hash:
            orders[order_id]["tx_hash"] = tx_hash
        _save(ctx, orders)
        ctx.logger.info(f"[orders] refunded {order_id} tx={tx_hash}")


def mark_error(ctx: Context, order_id: str, err: str) -> None:
    orders = _load(ctx)
    if order_id in orders:
        orders[order_id]["last_error"] = err
        orders[order_id]["attempts"] = int(orders[order_id].get("attempts") or 0) + 1
        _save(ctx, orders)
        ctx.logger.error(f"[orders] error {order_id}: {err}")


def set_tx_hash(ctx: Context, order_id: str, tx_hash: str) -> None:
    orders = _load(ctx)
    if order_id in orders:
        orders[order_id]["tx_hash"] = tx_hash
        _save(ctx, orders)
        ctx.logger.info(f"[orders] set_tx {order_id} -> {tx_hash}")


def set_notify(ctx: Context, order_id: str, agent_addr: str) -> None:
    orders = _load(ctx)
    if order_id in orders:
        orders[order_id]["notify_agent"] = agent_addr
        _save(ctx, orders)
        ctx.logger.info(f"[orders] set_notify {order_id} -> {agent_addr}")


def get_order(ctx: Context, order_id: str) -> Dict[str, Any] | None:
    return _load(ctx).get(order_id)
