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
