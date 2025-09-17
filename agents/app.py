import requests
from uagents import Agent, Context, Protocol
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from uuid import uuid4
from uagents_core.contrib.protocols.chat import (
    chat_protocol_spec,
    ChatMessage,
    ChatAcknowledgement,
    TextContent,
    StartSessionContent,
    ResourceContent,
    Resource,
)
import os
from dotenv import load_dotenv
import json
import qrcode
from io import BytesIO
import base64
from qrcode.image.pil import PilImage
from uagents_core.storage import ExternalStorage
from eth_abi import encode, decode
from eth_utils import keccak, to_checksum_address
from decimal import Decimal, ROUND_DOWN

load_dotenv()

# ASI1 Config

ASI1_API_KEY = os.getenv("ASI1_API_KEY")
ASI1_BASE_URL = "https://api.asi1.ai/v1"
ASI1_HEADERS = {
    "Authorization": f"Bearer {ASI1_API_KEY}",
    "Content-Type": "application/json",
}

# AgentVerse Config (for ExternalStorage, if needed)

AGENTVERSE_API_KEY = os.getenv("AGENTVERSE_API_KEY")
AGENTVERSE_URL = os.getenv("AGENTVERSE_URL", "https://agentverse.ai").rstrip("/")
STORAGE_URL = f"{AGENTVERSE_URL}/v1/storage"

external_storage = (
    ExternalStorage(api_token=AGENTVERSE_API_KEY, storage_url=STORAGE_URL)
    if AGENTVERSE_API_KEY
    else None
)

# BNB Chain Config

BSC_RPC_URL = os.getenv("BSC_RPC_URL")

if not ASI1_API_KEY:
    raise RuntimeError("ASI1_API_KEY not set. Add it to your environment or .env")
if not BSC_RPC_URL:
    raise RuntimeError("BSC_RPC_URL not set. Add it to your environment or .env")

# LST Tokens Config

LST_REGISTRY_BSC: List[Dict[str, Any]] = [
    {
        "symbol": "BNBx",
        "name": "Stader BNBx",
        "address": "0x1bdd3cf7f79cfb8edbb955f20ad99211551ba275",
        "project": "Stader",
        "coingecko_id": "stader-bnbx",
        "sources": [
            "https://binance.docs.staderlabs.com/bnbx-faqs/tokens-and-contract",
            "https://bscscan.com/token/0x1bdd3cf7f79cfb8edbb955f20ad99211551ba275",
        ],
    },
    {
        "symbol": "ANKRBNB",
        "name": "Ankr Staked BNB",
        "address": "0x52f24a5e03aee338da5fd9df68d2b6fae1178827",
        "project": "Ankr",
        "coingecko_id": "ankr-staked-bnb",
        "sources": [
            "https://www.ankr.com/docs/liquid-staking/bnb/overview/",
            "https://www.coingecko.com/en/coins/ankr-staked-bnb",
            "https://bscscan.com/token/0x52f24a5e03aee338da5fd9df68d2b6fae1178827",
        ],
    },
    {
        "symbol": "STKBNB",
        "name": "pSTAKE Staked BNB",
        "address": "0xc2e9d07f66a89c44062459a47a0d2dc038e4fb16",
        "project": "pSTAKE",
        "coingecko_id": "pstake-staked-bnb",
        "sources": [
            "https://www.coingecko.com/en/coins/pstake-staked-bnb",
            "https://bscscan.com/token/0xc2e9d07f66a89c44062459a47a0d2dc038e4fb16",
        ],
    },
]

# COINGECKO / GECKOTERMINAL / PANCAKESWAP INFO HELPERS

CG_BASE = "https://api.coingecko.com/api/v3"
GT_BASE = "https://api.geckoterminal.com/api/v2"
BINANCE_BASE = "https://api.binance.com"
PANCAKE_INFO_BASE = "https://api.pancakeswap.info/api/v2"
ROUTER_V2 = "0x10ED43C718714eb63d5aA57B78B54704E256024E"
CHAIN_ID = 56  # BNB Chain
WBNB_BSC = "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c".lower()
PANCAKE_SWAP_BASE = "https://pancakeswap.finance/swap"
DEFAULT_HEADERS = {
    "Accept": "application/json",
    "User-Agent": "bnb-chain-lst-agent/1.0 (+https://example.com)",
}


def _wei_from_bnb(amount_str: str) -> int:
    amt = Decimal(str(amount_str))
    if amt <= 0:
        raise ValueError("amount_bnb must be > 0")

    wei = (amt * (Decimal(10) ** 18)).to_integral_value(rounding=ROUND_DOWN)
    return int(wei)


def _selector(sig: str) -> bytes:
    return keccak(text=sig)[:4]


def _rpc_call(data_hex: str) -> str:
    payload = {
        "jsonrpc": "2.0",
        "method": "eth_call",
        "params": [{"to": ROUTER_V2, "data": data_hex}, "latest"],
        "id": 1,
    }
    r = requests.post(BSC_RPC_URL, json=payload, timeout=20)
    r.raise_for_status()
    j = r.json()
    if "error" in j:
        raise RuntimeError(f"eth_call error: {j['error']}")
    return j["result"]


def _rpc_call_generic(
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


def _rpc_call_router(data_hex: str) -> str:
    """
    eth_call to router (no value), used for getAmountsOut.
    """
    j = _rpc_call_generic(ROUTER_V2, data_hex, 0)
    if "error" in j:
        raise RuntimeError(f"eth_call error: {j['error']}")
    return j["result"]  # hex "0x..."


def _get_amount_out_min(amount_in_wei: int, path: list[str], slippage_bps: int) -> int:
    sel = _selector("getAmountsOut(uint256,address[])")
    calldata = sel + encode(["uint256", "address[]"], [amount_in_wei, path])
    data = "0x" + calldata.hex()

    res = _rpc_call_router(data)
    out_bytes = bytes.fromhex(res[2:])
    amounts = decode(["uint256[]"], out_bytes)[0]
    if len(amounts) < 2:
        raise RuntimeError("Router returned invalid amounts")
    amount_out = amounts[-1]

    if not (0 <= slippage_bps < 10_000):
        raise ValueError("slippage_bps must be in [0, 9999]")
    return (amount_out * (10_000 - slippage_bps)) // 10_000


def _build_swap_exact_eth_tx(
    amount_in_wei: int,
    amount_out_min: int,
    path: list[str],
    recipient: str,
    deadline_unix: int,
) -> dict:
    # swapExactETHForTokens(uint256,address[],address,uint256)
    sel = _selector("swapExactETHForTokens(uint256,address[],address,uint256)")
    calldata = sel + encode(
        ["uint256", "address[]", "address", "uint256"],
        [amount_out_min, path, to_checksum_address(recipient), deadline_unix],
    )
    return {
        "to": to_checksum_address(ROUTER_V2),
        "value": str(amount_in_wei),  # decimal string (wei)
        "data": "0x" + calldata.hex(),
    }


def _eip681_from_tx(tx: dict, chain_id: int = 56) -> str:
    return f"ethereum:{tx['to']}@{chain_id}?value={tx['value']}&data={tx['data']}"


def _fetch_pool_stats_bsc(token_addr: str) -> Dict[str, Any]:
    """
    Try to fetch top pool stats for the token from GeckoTerminal.
    Returns a dict with keys: { 'liquidity_usd', 'price_change_24h' } if available.
    """
    try:
        url = f"{GT_BASE}/networks/bsc/tokens/{to_checksum_address(token_addr)}?include=top_pools"
        r = requests.get(url, headers=DEFAULT_HEADERS, timeout=20)
        r.raise_for_status()
        j = r.json()
        included = j.get("included", []) or []

        # Pick the first included pool; prefer the one that contains WBNB if present
        chosen = None
        for it in included:
            if it.get("type") != "pool":
                continue
            attrs = it.get("attributes", {}) or {}
            # Heuristic: prefer a pool that mentions WBNB
            txt = json.dumps(attrs).lower()
            if WBNB_BSC in txt:
                chosen = attrs
                break
            if chosen is None:
                chosen = attrs

        if not chosen:
            return {}

        # GeckoTerminal uses various keys across DEXes; normalize best-effort
        liq = (
            chosen.get("reserve_in_usd")
            or chosen.get("reserve_usd")
            or chosen.get("liquidity_usd")
            or chosen.get("total_liquidity_usd")
            or chosen.get("pool_liquidity_usd")
        )
        chg = chosen.get("price_change_24h") or chosen.get(
            "price_change_percentage_24h"
        )

        liquidity_usd = float(liq) if liq is not None else None
        price_change_24h = float(chg) if chg is not None else None

        return {"liquidity_usd": liquidity_usd, "price_change_24h": price_change_24h}
    except Exception:
        return {}


def _auto_slippage_bps(token_addr: str) -> tuple[int, str]:
    """
    Decide slippage (in bps) based on pool liquidity and 24h price movement.
    Policy:
      - default 1.0% (100 bps)
      - widen to 1.5–2.0% if pool is shallow or 24h move is large
      - tighten to 0.5% on deep + calm pools
    """
    # Sensible, demo-friendly thresholds (tune as needed)
    DEEP_USD = 2_000_000  # ≥ $2M considered deep
    SHALLOW_USD = 200_000  # < $200k considered shallow
    VERY_SHALLOW_USD = 50_000  # < $50k very shallow
    LOW_VOL = 2.0  # ≤ 2% 24h move
    HIGH_VOL = 5.0  # ≥ 5% 24h move
    VERY_HIGH_VOL = 10.0  # ≥ 10% 24h move

    stats = _fetch_pool_stats_bsc(token_addr)
    liq = stats.get("liquidity_usd")
    vol = abs(stats.get("price_change_24h") or 0.0)

    # Defaults
    slippage = 100  # 1.00%
    reason = "default 1.0%"

    try:
        if liq is not None:
            if liq >= DEEP_USD and vol <= LOW_VOL:
                slippage = 50  # 0.50%
                reason = f"deep pool (~${liq:,.0f}) and low 24h move ({vol:.2f}%) → using 0.5%"
            elif liq < VERY_SHALLOW_USD or vol >= VERY_HIGH_VOL:
                slippage = 200  # 2.00%
                why = []
                if liq < VERY_SHALLOW_USD:
                    why.append(f"very low liquidity (~${liq:,.0f})")
                if vol >= VERY_HIGH_VOL:
                    why.append(f"high 24h move ({vol:.2f}%)")
                reason = f"{' & '.join(why)} → using 2.0%"
            elif liq < SHALLOW_USD or vol >= HIGH_VOL:
                slippage = 150  # 1.50%
                why = []
                if liq < SHALLOW_USD:
                    why.append(f"low liquidity (~${liq:,.0f})")
                if vol >= HIGH_VOL:
                    why.append(f"elevated 24h move ({vol:.2f}%)")
                reason = f"{' & '.join(why)} → using 1.5%"
            else:
                # Between shallow/deep and moderate volatility → stay at 1.0%
                slippage = 100
                reason = f"moderate liquidity (~${liq:,.0f}) and 24h move {vol:.2f}% → using 1.0%"
        else:
            # Couldn’t fetch pool stats — keep 1.0% but explain
            slippage = 100
            reason = "couldn’t fetch pool stats → using default 1.0%"
    except Exception as e:
        slippage = 100
        reason = f"autopilot error ({e}) → using default 1.0%"

    return slippage, reason


def fetch_bnb_price() -> Dict[str, Any]:
    """
    Returns {"bnb_usd": float, "source": str} without needing an API key.
    Tries CoinGecko (by id) -> GeckoTerminal (WBNB) -> PancakeSwap Info.
    """

    try:
        r = requests.get(
            f"{CG_BASE}/simple/price",
            params={"ids": "binancecoin", "vs_currencies": "usd", "precision": "full"},
            headers=DEFAULT_HEADERS,
            timeout=15,
        )
        r.raise_for_status()
        px = r.json().get("binancecoin", {}).get("usd")
        if px is not None:
            return {"bnb_usd": float(px), "source": "coingecko_id"}
    except Exception:
        pass
    try:
        r = requests.get(
            f"{GT_BASE}/simple/networks/bsc/token_price/{WBNB_BSC}",
            headers=DEFAULT_HEADERS,
            timeout=15,
        )
        r.raise_for_status()
        px_map = r.json().get("data", {}).get("attributes", {}).get("token_prices", {})
        px = px_map.get(WBNB_BSC)
        if px is not None:
            return {"bnb_usd": float(px), "source": "geckoterminal"}
    except Exception:
        pass
    try:
        r = requests.get(
            f"{PANCAKE_INFO_BASE}/tokens/{WBNB_BSC}",
            headers=DEFAULT_HEADERS,
            timeout=15,
        )
        r.raise_for_status()
        px = r.json().get("data", {}).get("price")
        if px is not None:
            return {"bnb_usd": float(px), "source": "pancakeswap_info"}
    except Exception:
        pass
    raise RuntimeError("Unable to fetch BNB/USD from public sources (CG/GT/Pancake).")


def get_bnb_info() -> Dict[str, Any]:
    """
    Returns current BNB price/info with fallbacks.
    Fields: symbol, name, coingecko_id, price_usd, change_24h_pct, last_updated, source, sources(list)
    """
    now_ts = int(datetime.now(tz=timezone.utc).timestamp())
    now_iso = datetime.fromtimestamp(now_ts, tz=timezone.utc).isoformat()

    try:
        r = requests.get(
            f"{CG_BASE}/simple/price",
            params={
                "ids": "binancecoin",
                "vs_currencies": "usd",
                "include_24hr_change": "true",
                "include_last_updated_at": "true",
                "precision": "full",
            },
            headers=DEFAULT_HEADERS,
            timeout=15,
        )
        r.raise_for_status()
        data = r.json().get("binancecoin", {}) or {}
        usd = data.get("usd")
        if usd is not None:
            return {
                "symbol": "BNB",
                "name": "BNB",
                "coingecko_id": "binancecoin",
                "price_usd": float(usd),
                "change_24h_pct": (
                    float(data.get("usd_24h_change"))
                    if data.get("usd_24h_change") is not None
                    else None
                ),
                "last_updated": datetime.fromtimestamp(
                    (
                        int(data.get("last_updated_at"))
                        if data.get("last_updated_at")
                        else now_ts
                    ),
                    tz=timezone.utc,
                ).isoformat(),
                "source": "coingecko_id",
                "sources": [
                    f"{CG_BASE}/simple/price?ids=binancecoin&vs_currencies=usd"
                ],
            }
    except Exception:
        pass

    try:
        r = requests.get(
            f"{GT_BASE}/simple/networks/bsc/token_price/{WBNB_BSC}",
            headers=DEFAULT_HEADERS,
            timeout=15,
        )
        r.raise_for_status()
        gt = r.json()
        px_map = gt.get("data", {}).get("attributes", {}).get("token_prices", {}) or {}
        px = px_map.get(WBNB_BSC)
        if px is not None:
            return {
                "symbol": "BNB",
                "name": "BNB (WBNB reference)",
                "coingecko_id": "binancecoin",
                "price_usd": float(px),
                "change_24h_pct": None,
                "last_updated": now_iso,
                "source": "geckoterminal",
                "sources": [f"{GT_BASE}/simple/networks/bsc/token_price/{WBNB_BSC}"],
            }
    except Exception:
        pass

    try:
        r = requests.get(
            f"{PANCAKE_INFO_BASE}/tokens/{WBNB_BSC}",
            headers=DEFAULT_HEADERS,
            timeout=15,
        )
        r.raise_for_status()
        info = r.json()
        px = info.get("data", {}).get("price")
        if px is not None:
            return {
                "symbol": "BNB",
                "name": "BNB (WBNB reference)",
                "coingecko_id": "binancecoin",
                "price_usd": float(px),
                "change_24h_pct": None,
                "last_updated": now_iso,
                "source": "pancakeswap_info",
                "sources": [f"{PANCAKE_INFO_BASE}/tokens/{WBNB_BSC}"],
            }
    except Exception:
        pass

    raise RuntimeError("Unable to fetch BNB price from public sources.")


def _upload_png_to_storage(
    ctx: Context, sender: str, png_bytes: bytes, mime: str = "image/png"
):
    if not external_storage:
        ctx.logger.error(
            "External storage not configured (AGENTVERSE_API_KEY or URL missing)."
        )
        return None, None, "storage_not_configured"
    asset_name = f"qr_{uuid4().hex}.png"
    try:
        asset_id = external_storage.create_asset(
            name=asset_name, content=png_bytes, mime_type=mime
        )
    except RuntimeError as err:
        ctx.logger.error(f"Asset creation failed: {err}")
        return None, None, f"create_failed:{err}"
    try:
        external_storage.set_permissions(asset_id=asset_id, agent_address=sender)
    except Exception as err:
        ctx.logger.error(f"set_permissions failed (non-fatal): {err}")
    asset_uri = f"agent-storage://{external_storage.storage_url}/{asset_id}"
    return asset_id, asset_uri, None


def _parse_approve_amount(amount: str | None) -> int:
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


def _eip681_for_approve(token_address: str, spender: str, value_uint256: int) -> str:
    """
    Build an EIP-681 URI for approve(spender, value).
    We include value=0 explicitly. Some wallets ignore 'value' for data-only calls.
    """
    token = to_checksum_address(token_address)
    spender = to_checksum_address(spender)
    sel = _selector("approve(address,uint256)")
    calldata = sel + encode(["address", "uint256"], [spender, value_uint256])
    # EIP-681 form: ethereum:<to>@<chain_id>?value=<wei>&data=0x...
    # For ERC20 approve, value is 0 (no native BNB sent).
    return f"ethereum:{token}@{CHAIN_ID}?value=0&data=0x{calldata.hex()}"


def _make_qr_png(data: str) -> tuple[bytes, str]:
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


def _find_token(symbol_or_address: str) -> Dict[str, Any]:
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


def simulate_swap(tx: dict) -> Dict[str, Any]:
    """
    eth_call the actual swap tx (to, data, value) to see if it would succeed.
    If success, many routers return encoded return data (amounts[]).
    If revert, return a human-friendly message.
    """
    try:
        j = _rpc_call_generic(
            to_addr=tx["to"], data_hex=tx["data"], value_dec_str=tx.get("value", "0")
        )
        if "error" in j:
            # Try to surface a readable error
            msg = j["error"].get("message", "execution reverted")
            # (Optionally parse j['error'].get('data') to decode Error(string))
            return {"ok": False, "revert": msg}
        raw = j.get("result", "0x")
        decoded = None
        amount_out = None
        try:
            # Most v2 routers return uint256[] amounts
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
    value_uint256 = _parse_approve_amount(amount)

    uri = _eip681_for_approve(token, spender, value_uint256)
    png_bytes, _ = _make_qr_png(uri)

    return {
        "ok": True,
        "uri": uri,
        "token": token,
        "spender": spender,
        "amount_uint256": str(value_uint256),
        "qr_png_b64": base64.b64encode(png_bytes).decode("ascii"),
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
    if slippage_bps is None:
        slippage_bps, slippage_reason = _auto_slippage_bps(token_addr)
    else:
        slippage_reason = "user-specified slippage"

    token = _find_token(symbol_or_address)
    token_addr = to_checksum_address(token["address"])
    wbnb = to_checksum_address("0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c")
    recipient = to_checksum_address(recipient_address)

    amount_in_wei = _wei_from_bnb(amount_bnb)
    path = [wbnb, token_addr]

    # Quote with slippage
    amount_out_min = _get_amount_out_min(amount_in_wei, path, slippage_bps)
    deadline = int(datetime.now(timezone.utc).timestamp()) + int(deadline_seconds)

    # Build actual tx
    tx = _build_swap_exact_eth_tx(
        amount_in_wei, amount_out_min, path, recipient, deadline
    )

    # === NEW: simulate BEFORE returning QR
    sim = simulate_swap(tx)

    # Build EIP-681 regardless (user can still choose to try)
    eip681 = _eip681_from_tx(tx, chain_id=CHAIN_ID)
    png_bytes, _ = _make_qr_png(eip681)

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
        "qr_png_b64": base64.b64encode(png_bytes).decode("ascii"),
        "mime_type": "image/png",
    }


def _cg_simple_price_by_ids(ids: List[str]) -> Dict[str, Dict[str, Any]]:
    """
    Price USD + 24h change by CoinGecko ID (not contract). No API key required.
    Returns { coingecko_id: {"usd": float, "usd_24h_change": float, "last_updated_at": ts} }
    """
    if not ids:
        return {}
    r = requests.get(
        f"{CG_BASE}/simple/price",
        params={
            "ids": ",".join(ids),
            "vs_currencies": "usd",
            "include_24hr_change": "true",
            "precision": "full",
        },
        timeout=20,
        headers={"Accept": "application/json"},
    )
    r.raise_for_status()
    data = r.json()
    now_ts = int(datetime.now(tz=timezone.utc).timestamp())
    out: Dict[str, Dict[str, Any]] = {}
    for cid, v in data.items():
        out[cid] = {
            "usd": float(v.get("usd")) if v.get("usd") is not None else None,
            "usd_24h_change": (
                float(v.get("usd_24h_change"))
                if v.get("usd_24h_change") is not None
                else None
            ),
            "last_updated_at": now_ts,
            "_source": "coingecko_ids",
        }
    return out


def _gt_simple_by_addresses(addresses: List[str]) -> Dict[str, Dict[str, Any]]:
    """
    GeckoTerminal: Prices by contract on BSC. No key required.
    Returns { address_lower: {"usd": float, "usd_24h_change": None, "last_updated_at": ts} }
    """
    if not addresses:
        return {}
    path_addrs = ",".join([a.lower() for a in addresses])
    r = requests.get(
        f"{GT_BASE}/simple/networks/bsc/token_price/{path_addrs}",
        timeout=20,
        headers={"Accept": "application/json"},
    )
    r.raise_for_status()
    data = r.json()
    prices_map = (
        data.get("data", {}).get("attributes", {}).get("token_prices", {}) or {}
    )
    out: Dict[str, Dict[str, Any]] = {}
    now_ts = int(datetime.now(tz=timezone.utc).timestamp())
    for addr, price_str in prices_map.items():
        try:
            usd = float(price_str)
        except Exception:
            usd = None
        out[addr.lower()] = {
            "usd": usd,
            "usd_24h_change": None,
            "last_updated_at": now_ts,
            "_source": "geckoterminal",
        }
    return out


def fetch_lst_prices_bsc(
    addresses: List[str], id_map: Dict[str, str]
) -> Dict[str, Dict[str, Any]]:
    """
    Mix: first tries CoinGecko IDs (no key) for those that have a coingecko_id,
    and for the rest uses GeckoTerminal by contract.
    – addresses: list of contracts (checksummed or lowercase)
    – id_map: { address_lower: coingecko_id }
    Returns a dict indexed by address_lower with fields "usd", "usd_24h_change", "last_updated_at".
    """

    ids = sorted(set([cid for cid in id_map.values() if cid]))
    cg_by_id = _cg_simple_price_by_ids(ids) if ids else {}

    need_addr = [a.lower() for a in addresses if not id_map.get(a.lower())]
    gt_by_addr = _gt_simple_by_addresses(need_addr) if need_addr else {}

    now_ts = int(datetime.now(tz=timezone.utc).timestamp())
    result: Dict[str, Dict[str, Any]] = {}
    for addr in [a.lower() for a in addresses]:
        cid = id_map.get(addr)
        if cid and cid in cg_by_id:
            result[addr] = {
                "usd": cg_by_id[cid]["usd"],
                "usd_24h_change": cg_by_id[cid]["usd_24h_change"],
                "last_updated_at": cg_by_id[cid]["last_updated_at"],
            }
        elif addr in gt_by_addr:
            result[addr] = gt_by_addr[addr]
        else:
            result[addr] = {
                "usd": None,
                "usd_24h_change": None,
                "last_updated_at": now_ts,
            }
    return result


def list_lst_tokens() -> List[Dict[str, Any]]:
    addrs = [t["address"] for t in LST_REGISTRY_BSC]
    id_map = {t["address"].lower(): t.get("coingecko_id") for t in LST_REGISTRY_BSC}
    prices = fetch_lst_prices_bsc(addrs, id_map)
    bnb_info = fetch_bnb_price()
    bnb_usd = bnb_info["bnb_usd"]

    now_iso = datetime.now(timezone.utc).isoformat()
    enriched: List[Dict[str, Any]] = []
    for t in LST_REGISTRY_BSC:
        addr = t["address"].lower()
        p = prices.get(addr, {})
        price_usd = float(p.get("usd")) if p.get("usd") is not None else None
        change_24h = (
            float(p.get("usd_24h_change"))
            if p.get("usd_24h_change") is not None
            else None
        )
        last_upd = p.get("last_updated_at")
        price_bnb = (
            (price_usd / bnb_usd) if (price_usd is not None and bnb_usd) else None
        )

        enriched.append(
            {
                "symbol": t["symbol"],
                "name": t["name"],
                "address": t["address"],
                "project": t["project"],
                "price_usd": price_usd,
                "price_bnb": price_bnb,
                "peg_ratio": price_bnb,
                "change_24h_pct": change_24h,
                "sources": t.get("sources", []),
                "last_updated": (
                    datetime.fromtimestamp(last_upd, tz=timezone.utc).isoformat()
                    if last_upd
                    else now_iso
                ),
            }
        )
    return enriched


tools = [
    {
        "type": "function",
        "function": {
            "name": "list_lst_tokens",
            "description": "Lists all supported LST tokens on BNB Chain with current price and relevant metadata.",
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_bnb_info",
            "description": "Returns current BNB price in USD, 24h change (if available), timestamp, and basic metadata.",
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_buy_lst_tx_qr",
            "description": "Create a QR with an EIP-681 URI that pre-fills a PancakeSwap v2 swapExactETHForTokens transaction for BNB→LST.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol_or_address": {"type": "string"},
                    "amount_bnb": {"type": "string"},
                    "recipient_address": {"type": "string"},
                    "slippage_bps": {
                        "type": "integer",
                        "description": "Optional. If omitted, agent uses Slippage Autopilot (0.5%–2.0% based on liquidity/volatility).",
                    },
                    "deadline_seconds": {"type": "integer"},
                },
                "required": ["symbol_or_address", "amount_bnb", "recipient_address"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_approve_qr",
            "description": "Create an ERC-20 approve() QR allowing the PancakeSwap v2 router to spend the given token.",
            "parameters": {
                "type": "object",
                "properties": {
                    "token_address": {
                        "type": "string",
                        "description": "ERC-20 address on BSC mainnet",
                    },
                    "amount": {
                        "type": "string",
                        "description": "Optional. 'max'/'unlimited' (default), hex 0x..., or decimal raw uint256.",
                    },
                },
                "required": ["token_address"],
                "additionalProperties": False,
            },
        },
    },
]


def dispatch_tool(
    func_name: str, _args: Dict[str, Any], ctx: Context
) -> Dict[str, Any]:
    try:
        if func_name == "list_lst_tokens":
            data = list_lst_tokens()
            return {"ok": True, "tokens": data}
        elif func_name == "get_bnb_info":
            data = get_bnb_info()
            return {"ok": True, "bnb": data}
        elif func_name == "create_buy_lst_tx_qr":
            data = create_buy_lst_tx_qr(
                _args["symbol_or_address"],
                _args["amount_bnb"],
                _args["recipient_address"],
                _args.get("deadline_seconds", 20 * 60),
            )
            return data
        elif func_name == "create_approve_qr":
            return create_approve_qr(_args["token_address"], _args.get("amount"))
        else:
            return {"ok": False, "error": f"Unsupported tool: {func_name}"}
    except Exception as e:
        ctx.logger.error(f"Tool {func_name} failed: {e}")
        return {"ok": False, "error": str(e)}


async def process_query(query: str, ctx: Context) -> str:
    try:
        user_message = {"role": "user", "content": query}
        system_message = {
            "role": "system",
            "content": (
                "You are an AI assistant called BNB-chain-LST-Agent. "
                "You are a BNB-chain liquid staking expert. "
                "You can generate EIP-681 QR codes for on-chain actions on BNB Chain. "
                "When the user asks for LST list or prices, call the function list_lst_tokens. "
                "When the user asks for BNB price or BNB info, call the function get_bnb_info. "
                "When the user wants to buy an LST, call the function create_buy_lst_tx_qr. "
                "When the user asks to approve a token allowance, call the function create_approve_qr "
                "with the token address and optional amount. If amount is omitted, use unlimited allowance."
                "Before proposing a swap transaction, always simulate it via eth_call and report pass/fail."
                "Here is the list of known LST tokens on BNB chain:\n"
                f"{LST_REGISTRY_BSC}"
            ),
        }

        payload = {
            "model": "asi1-mini",
            "messages": [system_message, user_message],
            "tools": tools,
            "tool_choice": "auto",
            "temperature": 0.2,
            "max_tokens": 1024,
        }

        resp = requests.post(
            f"{ASI1_BASE_URL}/chat/completions",
            headers=ASI1_HEADERS,
            json=payload,
            timeout=60,
        )
        resp.raise_for_status()
        response_json = resp.json()
        model_msg = response_json["choices"][0]["message"]

        messages_history = [system_message, user_message, model_msg]

        tool_calls = model_msg.get("tool_calls", []) or []

        for tc in tool_calls:
            func_name = tc["function"]["name"]
            args = json.loads(tc["function"].get("arguments") or "{}")
            tool_result = dispatch_tool(func_name, args, ctx)

            messages_history.append(
                {
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "name": func_name,
                    "content": json.dumps(tool_result),
                }
            )

            if func_name == "create_buy_lst_tx_qr" and tool_result.get("ok"):
                tok = tool_result["token"]["symbol"]
                amt = tool_result["amount_bnb"]
                slip = tool_result["slippage_bps"]
                uri = tool_result["uri"]
                sim = tool_result.get("simulation", {}) or {}
                if sim.get("ok"):
                    sim_line = "✅ **Simulation passed**"
                    if sim.get("amount_out") is not None:
                        sim_line += f" — estimated out (pre-slippage): `{sim['amount_out']}` (raw units)"
                else:
                    sim_line = (
                        f"⚠️ **Would revert:** {sim.get('revert','unknown error')}"
                    )

                slip = tool_result["slippage_bps"]
                slip_reason = tool_result.get("slippage_reason", "default 1.0%")

                text = (
                    f"I generated a raw swap transaction for **{amt} BNB → {tok}**.\n\n"
                    f"{sim_line}\n\n"
                    f"**Slippage:** {slip/100:.2f}% — _{slip_reason}_\n"
                    f"**Router:** `{ROUTER_V2}`\n"
                    f"**URI (EIP-681):** `{uri}`\n"
                    f"Scan the QR below to open **Confirm Transaction** in your wallet."
                )

                return {
                    "type": "qr",
                    "text": text,
                    "image": {
                        "b64": tool_result["qr_png_b64"],
                        "mime": tool_result.get("mime_type", "image/png"),
                        "name": f"swap_tx_{tok}_{amt}.png",
                    },
                }

            if func_name == "create_approve_qr" and tool_result.get("ok"):
                token = tool_result["token"]
                spender = tool_result["spender"]
                amt_raw = tool_result["amount_uint256"]
                uri = tool_result["uri"]

                # Human text + preview details
                text = (
                    f"Generated an **approve()** transaction QR.\n\n"
                    f"**Token:** `{token}`\n"
                    f"**Spender (Pancake v2 Router):** `{spender}`\n"
                    f"**Amount (raw uint256):** `{amt_raw}`\n"
                    f"**EIP-681 URI:** `{uri}`\n\n"
                    f"Scan to open the pre-filled **Confirm Transaction** in your wallet.\n"
                    f"(No BNB is sent — `value=0`.)"
                )

                return {
                    "type": "qr",
                    "text": text,
                    "image": {
                        "b64": tool_result["qr_png_b64"],
                        "mime": tool_result.get("mime_type", "image/png"),
                        "name": f"approve_{token}.png",
                    },
                }

        final = requests.post(
            f"{ASI1_BASE_URL}/chat/completions",
            headers=ASI1_HEADERS,
            json={
                "model": "asi1-mini",
                "messages": messages_history,
                "temperature": 0.2,
                "max_tokens": 2048,
            },
            timeout=60,
        )
        final.raise_for_status()
        return final.json()["choices"][0]["message"]["content"]

    except Exception as e:
        ctx.logger.error(f"Error processing query: {e}")
        return f"An error occurred: {e}"


def _text_msg(text: str) -> ChatMessage:
    return ChatMessage(
        timestamp=datetime.now(timezone.utc),
        msg_id=uuid4(),
        content=[TextContent(type="text", text=text)],
    )


def _resource_msg(asset_id: str, uri: str, mime: str) -> ChatMessage:
    return ChatMessage(
        timestamp=datetime.now(timezone.utc),
        msg_id=uuid4(),
        content=[
            ResourceContent(
                type="resource",
                resource_id=asset_id,
                resource=Resource(
                    uri=uri, metadata={"mime_type": mime, "role": "qr-code"}
                ),
            )
        ],
    )


# Agent and Protocol Setup

agent = Agent(name="bnb-chain-lst-agent", port=8001, mailbox=True)
chat_proto = Protocol(spec=chat_protocol_spec)


@chat_proto.on_message(model=ChatMessage)
async def handle_chat_message(ctx: Context, sender: str, msg: ChatMessage):
    try:
        ack = ChatAcknowledgement(
            timestamp=datetime.now(timezone.utc), acknowledged_msg_id=msg.msg_id
        )
        await ctx.send(sender, ack)

        for item in msg.content:
            if isinstance(item, StartSessionContent):
                ctx.logger.info(f"Got a start session message from {sender}")
                continue
            elif isinstance(item, TextContent):
                ctx.logger.info(f"Got a message from {sender}: {item.text}")

                result = await process_query(item.text, ctx)

                if isinstance(result, dict) and result.get("type") == "qr":
                    await ctx.send(sender, _text_msg(result["text"]))

                    img = result.get("image") or {}
                    b64 = img.get("b64")
                    mime = img.get("mime", "image/png")

                    if b64:
                        png_bytes = base64.b64decode(b64)
                        asset_id, asset_uri, err = _upload_png_to_storage(
                            ctx, sender, png_bytes, mime
                        )
                        if asset_id and asset_uri:
                            await ctx.send(
                                sender, _resource_msg(asset_id, asset_uri, mime)
                            )
                        else:
                            ctx.logger.error(f"Upload to storage failed: {err}")
                            fallback_text = (
                                result["text"]
                                + "\n\nI couldn’t attach the QR image due to a storage error. "
                                + "Here’s the direct PancakeSwap link instead:\n"
                                + result.get("url", "")
                            )
                            await ctx.send(sender, _text_msg(fallback_text))
                    else:
                        await ctx.send(sender, _text_msg(result["text"]))

                    continue

                response_text = (
                    result if isinstance(result, str) else json.dumps(result)
                )
                await ctx.send(sender, _text_msg(response_text))

            else:
                ctx.logger.info(f"Got unexpected content from {sender}")
    except Exception as e:
        ctx.logger.error(f"Error handling chat message: {str(e)}")
        error_response = ChatMessage(
            timestamp=datetime.now(timezone.utc),
            msg_id=uuid4(),
            content=[TextContent(type="text", text=f"An error occurred: {str(e)}")],
        )
        await ctx.send(sender, error_response)


@chat_proto.on_message(model=ChatAcknowledgement)
async def handle_chat_acknowledgement(
    ctx: Context, sender: str, msg: ChatAcknowledgement
):
    ctx.logger.info(
        f"Received acknowledgement from {sender} for message {msg.acknowledged_msg_id}"
    )
    if msg.metadata:
        ctx.logger.info(f"Metadata: {msg.metadata}")


agent.include(chat_proto)

if __name__ == "__main__":
    agent.run()
