from typing import Dict, Any
import requests
from eth_abi import encode, decode

from .config import BSC_RPC_URL, ROUTER_V2
from .utils import selector


def rpc(method: str, params: list) -> dict:
    r = requests.post(
        BSC_RPC_URL,
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
        timeout=20,
    )
    r.raise_for_status()
    return r.json()


def rpc_call_generic(
    to_addr: str, data_hex: str, value_dec_str: str | int = 0
) -> Dict[str, Any]:
    """
    Perform eth_call with {to, data, value}. Returns JSON result or error.
    """
    if isinstance(value_dec_str, str):
        value_int = int(value_dec_str) if value_dec_str else 0
    else:
        value_int = int(value_dec_str)
    payload = {
        "jsonrpc": "2.0",
        "method": "eth_call",
        "params": [
            {"to": to_addr, "data": data_hex, "value": hex(value_int)},
            "latest",
        ],
        "id": 1,
    }
    r = requests.post(BSC_RPC_URL, json=payload, timeout=20)
    r.raise_for_status()
    return r.json()


def rpc_call_router(data_hex: str) -> str:
    """
    eth_call to router (no value), used for getAmountsOut.
    """
    j = rpc_call_generic(ROUTER_V2, data_hex, 0)
    if "error" in j:
        raise RuntimeError(f"eth_call error: {j['error']}")
    return j["result"]


def get_amount_out_min(amount_in_wei: int, path: list[str], slippage_bps: int) -> int:
    sel = selector("getAmountsOut(uint256,address[])")
    calldata = sel + encode(["uint256", "address[]"], [amount_in_wei, path])
    data = "0x" + calldata.hex()

    res = rpc_call_router(data)
    out_bytes = bytes.fromhex(res[2:])
    amounts = decode(["uint256[]"], out_bytes)[0]
    if len(amounts) < 2:
        raise RuntimeError("Router returned invalid amounts")
    amount_out = amounts[-1]

    if not (0 <= slippage_bps < 10_000):
        raise ValueError("slippage_bps must be in [0, 9999]")
    return (amount_out * (10_000 - slippage_bps)) // 10_000


def simulate_swap(tx: dict) -> Dict[str, Any]:
    """
    eth_call the actual swap tx (to, data, value) to see if it would succeed.
    If success, many routers return encoded return data (amounts[]).
    If revert, return a human-friendly message.
    """
    try:
        j = rpc_call_generic(
            to_addr=tx["to"], data_hex=tx["data"], value_dec_str=tx.get("value", "0")
        )
        if "error" in j:
            msg = j["error"].get("message", "execution reverted")
            return {"ok": False, "revert": msg}
        raw = j.get("result", "0x")
        decoded = None
        amount_out = None
        try:
            amounts = decode(["uint256[]"], bytes.fromhex(raw[2:]))[0]
            decoded = [int(x) for x in amounts]
            if len(decoded) >= 2:
                amount_out = decoded[-1]
        except Exception:
            pass
        return {"ok": True, "result": raw, "amounts": decoded, "amount_out": amount_out}
    except requests.HTTPError as e:
        return {"ok": False, "revert": f"RPC HTTP error: {e}"}
    except Exception as e:
        return {"ok": False, "revert": f"Simulation error: {e}"}
