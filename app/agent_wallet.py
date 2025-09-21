# app/agent_wallet.py

from typing import Tuple, Optional
from eth_account import Account
from eth_account.signers.local import LocalAccount

from .config import AGENT_PRIV
from .rpc import rpc

Account.enable_unaudited_hdwallet_features()

_agent_acct: LocalAccount = Account.from_key(AGENT_PRIV)

def agent_address() -> str:
    return _agent_acct.address

def get_nonce(address: str) -> int:
    res = rpc("eth_getTransactionCount", [address, "latest"])
    return int(res["result"], 16)

def send_raw_tx(raw_hex: str) -> str:
    res = rpc("eth_sendRawTransaction", [raw_hex])
    if "error" in res:
        raise RuntimeError(res["error"].get("message", "sendRawTx failed"))
    return res["result"]

def sign_and_send_legacy_tx(tx: dict, private_key_hex: str) -> str:
    acct = Account.from_key(private_key_hex)
    signed = acct.sign_transaction(tx)
    return send_raw_tx("0x" + signed.rawTransaction.hex())

def get_balance_wei(address: str) -> int:
    res = rpc("eth_getBalance", [address, "latest"])
    return int(res["result"], 16)
