from decimal import Decimal
from typing import Optional
from uagents import Context
from eth_utils import to_checksum_address

from .orders_kv import list_pending, mark_complete, mark_error
from .rpc import get_amount_out_min, simulate_swap
from .tx_builders import build_swap_exact_eth_tx, estimate_gas_and_price
from .agent_wallet import get_nonce, get_balance_wei, send_raw_tx
from .config import (
    CHAIN_ID,
    GAS_BUDGET_MULTIPLIER,
    MIN_SWAP_VALUE_WEI,
    WBNB_BSC,
)
from hexbytes import HexBytes
from eth_account import Account

def _budget(gas_limit: int, gas_price: int) -> int:
    return int(Decimal(gas_limit * gas_price) * Decimal(str(GAS_BUDGET_MULTIPLIER)))

def _broadcast_legacy(
    final_tx: dict, gas_limit: int, gas_price: int, nonce: int, priv: str
) -> str:
    """
    Sign and broadcast a legacy tx (BSC). Robust across eth-account versions.
    """
    acct = Account.from_key(priv)
    norm = {
        "chainId": int(CHAIN_ID),
        "to": to_checksum_address(final_tx["to"]),
        "value": int(final_tx["value"]),
        "gas": int(gas_limit + max(20000, gas_limit // 10)),
        "gasPrice": int(gas_price),
        "nonce": int(nonce),
        "data": final_tx.get("data") or "0x",
    }
    signed = acct.sign_transaction(norm)

    raw_bytes = None

    if hasattr(signed, "rawTransaction"):
        raw_bytes = bytes(HexBytes(getattr(signed, "rawTransaction")))

    elif isinstance(signed, dict) and "rawTransaction" in signed:
        raw_bytes = bytes(HexBytes(signed["rawTransaction"]))
    elif hasattr(signed, "raw_transaction"):
        raw_bytes = bytes(HexBytes(getattr(signed, "raw_transaction")))

    elif isinstance(signed, (bytes, bytearray, HexBytes)):
        raw_bytes = bytes(HexBytes(signed))

    elif hasattr(signed, "to_bytes"):
        raw_bytes = signed.to_bytes()
    else:
        raise TypeError(f"Unsupported signed tx type: {type(signed)}")

    raw_hex = "0x" + HexBytes(raw_bytes).hex()
    return send_raw_tx(raw_hex)


def try_settle_one(ctx: Context, o: dict) -> Optional[str]:
    print(f"\n Checking order {o['id']}...")
    print(f"\n  recv_addr: {o['recv_addr']}")
    bal = get_balance_wei(o["recv_addr"])
    if bal < MIN_SWAP_VALUE_WEI:
        print(f"  balance {bal} wei < min {MIN_SWAP_VALUE_WEI} wei, skipping")
        return None  # not funded yet

    print(f"\n Settling order {o['id']} with balance {bal} wei...")
    path = [to_checksum_address(WBNB_BSC), to_checksum_address(o["token_address"])]

    print("\n  estimating gas...")

    try:
        dummy_min = get_amount_out_min(bal, path, o["slippage_bps"])
    except Exception as e:
        raise RuntimeError(
            f"path not tradable on this network (WBNB->{o['token_address']}): {e}"
        )

    dummy_tx = build_swap_exact_eth_tx(
        bal, dummy_min, path, o["recipient"], deadline_unix=2**31 - 1
    )

    print("\n  simulating gas...")

    gas_limit, gas_price, gas_err = estimate_gas_and_price(
        dummy_tx, from_address=o["recv_addr"]
    )
    if gas_limit is None or gas_price is None:
        raise RuntimeError(f"gas estimation failed: {gas_err or 'unknown'}")

    print(f"\n  estimated gas limit: {gas_limit}, gas price: {gas_price} wei")

    gas_budget = _budget(gas_limit, gas_price)
    amount_in = bal - gas_budget
    if amount_in <= 0:
        return None

    print(f"\n  gas budget: {gas_budget} wei, amount_in: {amount_in} wei")
    amount_out_min = get_amount_out_min(amount_in, path, o["slippage_bps"])
    final_tx = build_swap_exact_eth_tx(
        amount_in, amount_out_min, path, o["recipient"], deadline_unix=2**31 - 1
    )

    print(f"\n  final tx: {final_tx}")

    sim = simulate_swap(final_tx)
    if not sim.get("ok"):
        raise RuntimeError(f"swap would revert: {sim.get('revert','unknown')}")

    print(f"\n  simulation ok: {sim}")
    nonce = get_nonce(o["recv_addr"])
    print(f"\n  using nonce: {nonce}")
    signed = {
        "chainId": CHAIN_ID,
        "to": final_tx["to"],
        "value": int(final_tx["value"]),
        "data": final_tx["data"],
        "gas": int(gas_limit * 1.1),
        "gasPrice": int(gas_price),
        "nonce": nonce,
    }
    txh = _broadcast_legacy(final_tx, gas_limit, gas_price, nonce, o["recv_priv"])
    print(f"\n  sent tx: {txh} \n")
    return txh


async def settlement_tick(ctx: Context):
    print("\n Settlement tick...")
    print("\n Pending orders:", list_pending(ctx))
    for o in list_pending(ctx):
        try:
            print(f"\n Trying to settle order {o['id']}...")
            txh = try_settle_one(ctx, o)
            if txh:
                mark_complete(ctx, o["id"])
                ctx.logger.info(f"Settled order {o['id']} → {txh}")
        except Exception as e:
            mark_error(ctx, o["id"], str(e))
            ctx.logger.error(f"Order {o['id']} failed: {e}")
