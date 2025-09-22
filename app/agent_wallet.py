from typing import Dict, Any
from eth_account import Account
from eth_account.datastructures import SignedTransaction as EASignedTx
from eth_utils import to_checksum_address
from hexbytes import HexBytes

from .rpc import rpc
from .config import CHAIN_ID

Account.enable_unaudited_hdwallet_features()


def get_nonce(address: str) -> int:
    j = rpc("eth_getTransactionCount", [to_checksum_address(address), "pending"])
    if "error" in j:
        raise RuntimeError(j["error"].get("message", "nonce error"))
    return int(j["result"], 16)


def get_balance_wei(address: str) -> int:
    j = rpc("eth_getBalance", [to_checksum_address(address), "latest"])
    if "error" in j:
        raise RuntimeError(j["error"].get("message", "balance error"))
    return int(j["result"], 16)


def send_raw_tx(raw_hex: str) -> str:
    j = rpc("eth_sendRawTransaction", [raw_hex])
    if "error" in j:
        raise RuntimeError(j["error"].get("message", "eth_sendRawTransaction error"))
    return j["result"]


def _normalize_legacy_tx(tx: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize a legacy (pre-1559) tx dict for BSC/BSC testnet:
    - ints for gas/gasPrice/value/nonce
    - checksum 'to'
    - ensure chainId set
    """
    return {
        "chainId": int(tx.get("chainId") or CHAIN_ID),
        "to": to_checksum_address(tx["to"]) if tx.get("to") else None,
        "value": int(tx.get("value") or 0),
        "gas": int(tx["gas"]),
        "gasPrice": int(tx["gasPrice"]),
        "nonce": int(tx["nonce"]),
        "data": tx.get("data") or "0x",
    }


def _extract_raw_tx(signed) -> str:
    """
    Accepts eth-account return types:
    - SignedTransaction (preferred path)
    - bytes / bytearray / HexBytes
    - dict with 'rawTransaction'
    - object with .rawTransaction
    """
    raw_bytes = None

    if isinstance(signed, EASignedTx):
        raw_bytes = bytes(HexBytes(signed.rawTransaction))

    elif isinstance(signed, (bytes, bytearray, HexBytes)):
        raw_bytes = bytes(HexBytes(signed))

    else:
        for accessor in (
            lambda s: getattr(s, "rawTransaction"),
            lambda s: s["rawTransaction"],
            lambda s: s.get("rawTransaction"),
        ):
            try:
                val = accessor(signed)
                if val is not None:
                    raw_bytes = bytes(HexBytes(val))
                    break
            except Exception:
                pass

    if raw_bytes is None:
        if hasattr(signed, "to_bytes"):
            raw_bytes = signed.to_bytes()
        else:
            raise TypeError(f"Unsupported signed tx type: {type(signed)}")

    return "0x" + HexBytes(raw_bytes).hex()


def sign_and_send_legacy_tx(tx: Dict[str, Any], private_key_hex: str) -> str:
    """
    Signs and broadcasts a legacy tx on BSC/BSC testnet.
    Robust across eth-account versions.
    """
    acct = Account.from_key(private_key_hex)
    norm = _normalize_legacy_tx(tx)
    signed = acct.sign_transaction(norm)
    raw_hex = _extract_raw_tx(signed)
    return send_raw_tx(raw_hex)
