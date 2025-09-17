from typing import Dict, Any, Tuple
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN
import base64
from io import BytesIO

import qrcode
from qrcode.image.pil import PilImage
from eth_utils import keccak, to_checksum_address

from .registry import LST_REGISTRY_BSC
from .config import CHAIN_ID


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


def make_qr_png(data: str) -> tuple[bytes, str]:
    """
    Create a PNG QR and return (png_bytes, data_url).
    """
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img: PilImage = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    png_bytes = buf.getvalue()
    data_url = "data:image/png;base64," + base64.b64encode(png_bytes).decode("ascii")
    return png_bytes, data_url


def find_token(symbol_or_address: str) -> Dict[str, Any]:
    s = symbol_or_address.strip().lower()
    for t in LST_REGISTRY_BSC:
        if t["address"].lower() == s:
            return t
    for t in LST_REGISTRY_BSC:
        if t["symbol"].lower() == s:
            return t
    raise ValueError(
        f"Unsupported token '{symbol_or_address}'. Allowed: {[t['symbol'] for t in LST_REGISTRY_BSC]}"
    )


def parse_approve_amount(amount: str | None) -> int:
    """
    Parse 'amount' for approve():
      - None / 'max' / 'unlimited' -> uint256 max
      - '0x...' -> hex
      - decimal string -> raw uint256 (token base units). No decimals scaling here.
    """
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
