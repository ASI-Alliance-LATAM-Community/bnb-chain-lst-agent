from typing import Dict, Any
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN
from eth_utils import keccak

from .config import CHAIN_ID, IS_DEV
from .registry import LST_REGISTRY_BSC

try:
    from .registry_dev import LST_REGISTRY_BSC_DEV
except Exception:
    LST_REGISTRY_BSC_DEV = []


def _active_registry():
    return LST_REGISTRY_BSC_DEV if IS_DEV and LST_REGISTRY_BSC_DEV else LST_REGISTRY_BSC


def find_token(symbol_or_address: str) -> Dict[str, Any]:
    s = symbol_or_address.strip().lower()
    reg = _active_registry()

    for t in reg:
        if t["address"].lower() == s:
            return t

    for t in reg:
        if t["symbol"].lower() == s:
            return t

    for t in reg:
        for a in t.get("aliases") or []:
            if str(a).lower() == s:
                return t

    allowed = [t["symbol"] for t in reg]
    raise ValueError(
        f"Unsupported token '{symbol_or_address}'. Allowed on this network: {allowed}"
    )


def wei_from_bnb(amount_str: str) -> int:
    amt = Decimal(str(amount_str))
    if amt <= 0:
        raise ValueError("amount_bnb must be > 0")
    wei = (amt * (Decimal(10) ** 18)).to_integral_value(rounding=ROUND_DOWN)
    return int(wei)


def selector(sig: str) -> bytes:
    return keccak(text=sig)[:4]


def eip681_from_tx(
    tx: dict, chain_id: int = 56, gas: int | None = None, gas_price: int | None = None
) -> str:
    base = f"ethereum:{tx['to']}@{chain_id}?value={tx['value']}&data={tx['data']}"
    if gas is not None:
        base += f"&gas={gas}"
    if gas_price is not None:
        base += f"&gasPrice={gas_price}"
    return base


def parse_approve_amount(amount: str | None) -> int:
    if amount is None:
        return (1 << 256) - 1
    a = str(amount).strip().lower()
    if a in ("max", "unlimited"):
        return (1 << 256) - 1
    if a.startswith("0x"):
        return int(a, 16)
    return int(a)


def now_ts() -> int:
    return int(datetime.now(timezone.utc).timestamp())
