# app/managed_buy.py

import base64
from uagents import Context
from eth_utils import to_checksum_address

from .utils import find_token
from .orders_kv import create_order
from .slippage import auto_slippage_bps
from .config import CHAIN_ID

def create_managed_buy(ctx: Context, symbol_or_address: str, recipient_address: str, slippage_bps: int | None = None):
    t = find_token(symbol_or_address)
    token_addr = to_checksum_address(t["address"])
    recip = to_checksum_address(recipient_address)

    sbps, reason = auto_slippage_bps(token_addr) if slippage_bps is None else (slippage_bps, "user-specified")
    order = create_order(ctx, t["symbol"], token_addr, recip, sbps)

    pay_addr = order["recv_addr"]
    uri = f"ethereum:{pay_addr}@{CHAIN_ID}"  # super-compatible “pay to address” URI

    return {
        "ok": True,
        "uri": uri,
        "mime_type": "image/png",
        "order_id": order["id"],
        "recv_addr": pay_addr,
        "slippage_bps": sbps,
        "slippage_reason": reason,
        "notes": [
            "Scan the QR → Send BNB to the order address.",
            "Amount can be any; include enough for gas.",
            "Agent swaps BNB→LST and delivers tokens to your address.",
        ],
    }
