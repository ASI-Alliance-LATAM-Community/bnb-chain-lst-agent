from decimal import Decimal
from typing import Optional
from uagents import Context
from eth_account import Account
from hexbytes import HexBytes
from eth_utils import to_checksum_address

from .orders_kv import (
    list_active,
    mark_complete,
    mark_error,
    set_tx_hash,
    mark_refund_pending,
    mark_refunded,
)
from .rpc import get_amount_out_min, simulate_swap, rpc
from .tx_builders import build_swap_exact_eth_tx, estimate_gas_and_price
from .agent_wallet import get_nonce, get_balance_wei, send_raw_tx
from .config import (
    CHAIN_ID,
    GAS_BUDGET_MULTIPLIER,
    MIN_SWAP_VALUE_WEI,
    WBNB_BSC,
)


def _budget(gas_limit: int, gas_price: int) -> int:
    return int(Decimal(gas_limit * gas_price) * Decimal(str(GAS_BUDGET_MULTIPLIER)))


def _broadcast_legacy(
    final_tx: dict, gas_limit: int, gas_price: int, nonce: int, priv: str, ctx: Context
) -> str:
    acct = Account.from_key(priv)
    norm = {
        "chainId": int(CHAIN_ID),
        "to": to_checksum_address(final_tx["to"]),
        "value": int(final_tx["value"]),
        "gas": int(gas_limit + max(20_000, gas_limit // 10)),
        "gasPrice": int(gas_price),
        "nonce": int(nonce),
        "data": final_tx.get("data") or "0x",
    }
    signed = acct.sign_transaction(norm)
    if hasattr(signed, "rawTransaction"):
        raw_bytes = bytes(HexBytes(getattr(signed, "rawTransaction")))
    elif isinstance(signed, (bytes, bytearray, HexBytes)):
        raw_bytes = bytes(HexBytes(signed))
    elif hasattr(signed, "raw_transaction"):
        raw_bytes = bytes(HexBytes(getattr(signed, "raw_transaction")))
    else:
        raise TypeError(f"Unsupported signed tx type: {type(signed)}")
    ctx.logger.info(f"\n  signed raw tx: 0x{HexBytes(raw_bytes).hex()}\n")
    return send_raw_tx("0x" + HexBytes(raw_bytes).hex())


def _gas_price_safe() -> int:
    try:
        gp = rpc("eth_gasPrice", [])
        if "error" in gp:
            raise RuntimeError(gp["error"].get("message", "gasPrice error"))
        return int(gp["result"], 16)
    except Exception:
        return 1_000_000_000


def _build_refund_tx(to_addr: str, value_wei: int) -> dict:
    return {
        "to": to_checksum_address(to_addr),
        "value": int(value_wei),
        "data": "0x",
    }


def _estimate_refund_cost(from_addr: str) -> tuple[int, int, int]:
    """
    Returns (gas_limit, gas_price, budget) for a simple native transfer.
    """
    gas_price = _gas_price_safe()
    gas_limit = 30_000
    budget = _budget(gas_limit, gas_price)
    return gas_limit, gas_price, budget


def _try_refund(ctx: Context, o: dict) -> Optional[str]:
    """
    Try to refund remaining BNB from recv_addr back to recipient.
    Returns tx hash if broadcasted, None if not enough to cover gas.
    """
    bal = get_balance_wei(o["recv_addr"])
    if bal <= 0:
        return None
    gas_limit, gas_price, budget = _estimate_refund_cost(o["recv_addr"])
    amount = bal - budget
    if amount <= 0:
        return None

    tx = _build_refund_tx(o["recipient"], amount)
    nonce = get_nonce(o["recv_addr"])
    txh = _broadcast_legacy(tx, gas_limit, gas_price, nonce, o["recv_priv"], ctx)
    ctx.logger.info(f"Refund tx sent for order {o['id']} → {txh} (amount {amount} wei)")
    return txh


async def try_settle_one(ctx: Context, o: dict) -> Optional[str]:
    ctx.logger.info(f"\n Checking order {o['id']}...")
    ctx.logger.info(f"\n  recv_addr: {o['recv_addr']}")
    bal = get_balance_wei(o["recv_addr"])

    if o.get("status") == "refund_pending":
        txh = _try_refund(ctx, o)
        if txh:
            mark_refunded(ctx, o["id"], tx_hash=txh)
        else:
            mark_refund_pending(ctx, o["id"], "awaiting funds for refund gas")
        return None

    if bal < MIN_SWAP_VALUE_WEI:
        ctx.logger.info(f"  balance {bal} wei < min {MIN_SWAP_VALUE_WEI} wei, skipping")
        return None

    ctx.logger.info(f"\n Settling order {o['id']} with balance {bal} wei...")
    path = [to_checksum_address(WBNB_BSC), to_checksum_address(o["token_address"])]

    ctx.logger.info("\n  estimating gas...")
    dummy_min = get_amount_out_min(bal, path, o["slippage_bps"])
    dummy_tx = build_swap_exact_eth_tx(
        bal, dummy_min, path, o["recipient"], deadline_unix=2**31 - 1
    )

    ctx.logger.info("\n  simulating gas...")
    gas_limit, gas_price, gas_err = estimate_gas_and_price(
        dummy_tx, from_address=o["recv_addr"]
    )
    if gas_limit is None or gas_price is None:
        err = f"gas estimation failed: {gas_err or 'unknown'}"
        mark_error(ctx, o["id"], err)
        txh = _try_refund(ctx, o)
        if txh:
            mark_refunded(ctx, o["id"], tx_hash=txh)
        else:
            mark_refund_pending(ctx, o["id"], err)
        return None

    ctx.logger.info(f"\n  estimated gas limit: {gas_limit}, gas price: {gas_price} wei")

    gas_budget = _budget(gas_limit, gas_price)
    amount_in = bal - gas_budget
    if amount_in <= 0:
        txh = _try_refund(ctx, o)
        if txh:
            mark_refunded(ctx, o["id"], tx_hash=txh)
        else:
            mark_refund_pending(ctx, o["id"], "insufficient for swap; refund pending")
        return None

    ctx.logger.info(f"\n  gas budget: {gas_budget} wei, amount_in: {amount_in} wei")
    amount_out_min = get_amount_out_min(amount_in, path, o["slippage_bps"])
    final_tx = build_swap_exact_eth_tx(
        amount_in, amount_out_min, path, o["recipient"], deadline_unix=2**31 - 1
    )

    ctx.logger.info(f"\n  final tx: {final_tx}")

    sim = simulate_swap(final_tx)
    if not sim.get("ok"):
        err = f"swap would revert: {sim.get('revert','unknown')}"
        mark_error(ctx, o["id"], err)
        txh = _try_refund(ctx, o)
        if txh:
            mark_refunded(ctx, o["id"], tx_hash=txh)
        else:
            mark_refund_pending(ctx, o["id"], err)
        return None

    ctx.logger.info(f"\n  simulation ok: {sim}")

    nonce = get_nonce(o["recv_addr"])
    ctx.logger.info(f"\n  using nonce: {nonce}")

    txh = _broadcast_legacy(final_tx, gas_limit, gas_price, nonce, o["recv_priv"], ctx)
    ctx.logger.info(f"\n  sent tx: {txh} \n")
    return txh


async def settlement_tick(ctx: Context):
    ctx.logger.info("\n Settlement tick...")
    pending = list_active(ctx)
    ctx.logger.info(f"\n Pending orders: {pending}")

    for o in pending:
        try:
            ctx.logger.info(f"\n Trying to settle order {o['id']}...")
            txh = await try_settle_one(ctx, o)

            if txh:
                set_tx_hash(ctx, o["id"], txh)
                mark_complete(ctx, o["id"], tx_hash=txh)
                ctx.logger.info(f"Settled order {o['id']} → {txh}")

        except Exception as e:
            mark_error(ctx, o["id"], str(e))
            mark_refund_pending(ctx, o["id"], str(e))
            ctx.logger.error(f"Order {o['id']} failed and set to refund_pending: {e}")
