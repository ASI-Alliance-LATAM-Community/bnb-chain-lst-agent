# app/settlement.py

from decimal import Decimal
from typing import Optional
from uagents import Context
from eth_utils import to_checksum_address

from .orders_kv import list_pending, mark_complete, mark_error
from .rpc import get_amount_out_min, simulate_swap
from .tx_builders import build_swap_exact_eth_tx, estimate_gas_and_price
from .agent_wallet import get_nonce, sign_and_send_legacy_tx, get_balance_wei
from .config import CHAIN_ID, GAS_BUDGET_MULTIPLIER, MIN_SWAP_VALUE_WEI

def _budget(gas_limit: int, gas_price: int) -> int:
    return int(Decimal(gas_limit * gas_price) * Decimal(str(GAS_BUDGET_MULTIPLIER)))

def try_settle_one(ctx: Context, o: dict) -> Optional[str]:
    bal = get_balance_wei(o["recv_addr"])
    if bal < MIN_SWAP_VALUE_WEI:
        return None  # not funded yet

    path = [
        to_checksum_address("0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c"),
        to_checksum_address(o["token_address"]),
    ]

    dummy_min = get_amount_out_min(bal, path, o["slippage_bps"])
    dummy_tx  = build_swap_exact_eth_tx(bal, dummy_min, path, o["recipient"], deadline_unix=2**31-1)

    gas_limit, gas_price, gas_err = estimate_gas_and_price(dummy_tx, from_address=o["recv_addr"])
    if gas_limit is None or gas_price is None:
        raise RuntimeError(f"gas estimation failed: {gas_err or 'unknown'}")

    gas_budget = _budget(gas_limit, gas_price)
    amount_in  = bal - gas_budget
    if amount_in <= 0:
        return None

    amount_out_min = get_amount_out_min(amount_in, path, o["slippage_bps"])
    final_tx = build_swap_exact_eth_tx(amount_in, amount_out_min, path, o["recipient"], deadline_unix=2**31-1)

    sim = simulate_swap(final_tx)
    if not sim.get("ok"):
        raise RuntimeError(f"swap would revert: {sim.get('revert','unknown')}")

    nonce = get_nonce(o["recv_addr"])
    signed = {
        "chainId": CHAIN_ID,
        "to": final_tx["to"],
        "value": int(final_tx["value"]),
        "data": final_tx["data"],
        "gas": int(gas_limit * 1.1),
        "gasPrice": int(gas_price),
        "nonce": nonce,
    }
    txh = sign_and_send_legacy_tx(signed, o["recv_priv"])
    return txh

async def settlement_tick(ctx: Context):
    for o in list_pending(ctx):
        try:
            txh = try_settle_one(ctx, o)
            if txh:
                mark_complete(ctx, o["id"])
                ctx.logger.info(f"Settled order {o['id']} → {txh}")
        except Exception as e:
            mark_error(ctx, o["id"], str(e))
            ctx.logger.error(f"Order {o['id']} failed: {e}")
