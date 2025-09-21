from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
import base64
from eth_abi import encode
from eth_utils import to_checksum_address

from .config import ROUTER_V2, CHAIN_ID
from .utils import (
    selector,
    wei_from_bnb,
    eip681_from_tx,
    find_token,
    parse_approve_amount,
)
from .rpc import get_amount_out_min, simulate_swap, rpc
from .slippage import auto_slippage_bps


def estimate_gas_and_price(
    tx: dict, from_address: str
) -> tuple[int | None, int | None, str | None]:
    """
    Returns (gas_limit, gas_price, err). On failure, (None, None, "reason")
    """
    try:
        call_obj = {
            "from": to_checksum_address(from_address),
            "to": to_checksum_address(tx["to"]),
            "data": tx["data"],
            "value": hex(int(tx.get("value", "0"))),
        }
        eg = rpc("eth_estimateGas", [call_obj])
        if "error" in eg:
            return None, None, f"estimateGas error: {eg['error'].get('message')}"
        gas_limit = int(eg.get("result", "0x0"), 16)

        gp = rpc("eth_gasPrice", [])
        if "error" in gp:
            return gas_limit, None, f"gasPrice error: {gp['error'].get('message')}"
        gas_price = int(gp.get("result", "0x0"), 16)

        return gas_limit, gas_price, None
    except Exception as e:
        return None, None, f"estimation exception: {e}"


def build_swap_exact_eth_tx(
    amount_in_wei: int,
    amount_out_min: int,
    path: list[str],
    recipient: str,
    deadline_unix: int,
) -> dict:
    sel = selector("swapExactETHForTokens(uint256,address[],address,uint256)")
    calldata = sel + encode(
        ["uint256", "address[]", "address", "uint256"],
        [amount_out_min, path, to_checksum_address(recipient), deadline_unix],
    )
    return {
        "to": to_checksum_address(ROUTER_V2),
        "value": str(amount_in_wei),
        "data": "0x" + calldata.hex(),
    }


def eip681_for_approve(token_address: str, spender: str, value_uint256: int) -> str:
    """
    Build an EIP-681 URI for approve(spender, value).
    We include value=0 explicitly. Some wallets ignore 'value' for data-only calls.
    """
    token = to_checksum_address(token_address)
    spender = to_checksum_address(spender)
    sel = selector("approve(address,uint256)")
    calldata = sel + encode(["address", "uint256"], [spender, value_uint256])
    return f"ethereum:{token}@{CHAIN_ID}?value=0&data=0x{calldata.hex()}"


def create_approve_qr(token_address: str, amount: str | None = None) -> Dict[str, Any]:
    """
    Create a QR with an EIP-681 URI that pre-fills an ERC-20 approve() call:
      approve(ROUTER_V2, amount)

    Args:
      token_address: ERC-20 contract on BSC.
      amount: 'max'/'unlimited' (default), hex '0x..', or decimal raw uint256.

    Returns:
      { ok, uri, token, spender, amount_uint256, qr_png_b64, mime_type }
    """
    token = to_checksum_address(token_address)
    spender = to_checksum_address(ROUTER_V2)
    value_uint256 = parse_approve_amount(amount)

    uri = eip681_for_approve(token, spender, value_uint256)

    return {
        "ok": True,
        "uri": uri,
        "token": token,
        "spender": spender,
        "amount_uint256": str(value_uint256),
        "mime_type": "image/png",
        "notes": [
            "Scan with MetaMask mobile (or compatible wallet) to open a pre-filled Confirm Transaction.",
            "Function: approve(spender, value) on the token contract.",
            "Chain: BNB Smart Chain (chainId 56).",
            "No native BNB is sent (value=0).",
        ],
    }


def create_buy_lst_tx_qr(
    symbol_or_address: str,
    amount_bnb: str,
    recipient_address: str,
    slippage_bps: Optional[int] = None,
    deadline_seconds: int = 20 * 60,
    from_address: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Builds a raw transaction for PancakeSwap v2 swapExactETHForTokens and returns a QR
    that encodes an EIP-681 URI (ethereum:<router>@56?value=...&data=0x...).
    Scanning opens a Confirm Transaction screen in the wallet.

    - symbol_or_address: LST symbol from registry or exact token address
    - amount_bnb: e.g. "0.001"
    - recipient_address: destination EOA (user's address)
    - slippage_bps: e.g. 100 = 1%
    - deadline_seconds: from now
    """
    token = find_token(symbol_or_address)
    token_addr = to_checksum_address(token["address"])
    wbnb = to_checksum_address("0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c")
    recipient = to_checksum_address(recipient_address)
    sender_for_estimate = to_checksum_address(from_address or recipient_address)

    if slippage_bps is None:
        slippage_bps, slippage_reason = auto_slippage_bps(token_addr)
    else:
        slippage_reason = "user-specified slippage"

    amount_in_wei = wei_from_bnb(amount_bnb)
    path = [wbnb, token_addr]

    amount_out_min = get_amount_out_min(amount_in_wei, path, slippage_bps)
    deadline = int(datetime.now(timezone.utc).timestamp()) + int(deadline_seconds)

    tx = build_swap_exact_eth_tx(
        amount_in_wei, amount_out_min, path, recipient, deadline
    )

    sim = simulate_swap(tx)
    gas_limit, gas_price, gas_err = estimate_gas_and_price(tx, sender_for_estimate)

    eip681 = eip681_from_tx(tx, chain_id=CHAIN_ID, gas=gas_limit, gas_price=gas_price)

    meta_notes = [
        f"Slippage: {slippage_bps/100:.2f}% — {slippage_reason}",
        f"Gas estimate: {gas_limit or 'n/a'} | Gas price (wei): {gas_price or 'n/a'}",
        *([f"Gas estimation note: {gas_err}"] if gas_err else []),
        "Router: PancakeSwap v2",
    ]

    return {
        "ok": True,
        "uri": eip681,
        "tx": tx,
        "token": {"symbol": token["symbol"], "address": token_addr},
        "amount_bnb": amount_bnb,
        "slippage_bps": slippage_bps,
        "slippage_reason": slippage_reason,
        "deadline": deadline,
        "simulation": sim,
        "mime_type": "image/png",
        "gas_limit": gas_limit,
        "gas_price": gas_price,
        "gas_error": gas_err,
        "notes": meta_notes,
    }
