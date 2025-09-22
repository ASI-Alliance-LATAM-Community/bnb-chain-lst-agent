from eth_abi import encode
from eth_utils import to_checksum_address, keccak
from .rpc import rpc_call_generic

def _sel(sig: str) -> bytes:
    return keccak(text=sig)[:4]

def erc20_balance_of(token: str, owner: str) -> int:
    data = _sel("balanceOf(address)") + encode(["address"], [to_checksum_address(owner)])
    j = rpc_call_generic(to_checksum_address(token), "0x" + data.hex(), 0)
    if "error" in j:
        raise RuntimeError(j["error"].get("message", "balanceOf error"))
    return int(j["result"], 16)

def erc20_decimals(token: str) -> int:
    data = _sel("decimals()")
    j = rpc_call_generic(to_checksum_address(token), "0x" + data.hex(), 0)
    if "error" in j:
        raise RuntimeError(j["error"].get("message", "decimals error"))
    return int(j["result"], 16)
