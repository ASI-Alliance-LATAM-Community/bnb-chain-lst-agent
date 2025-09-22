from typing import Dict, Any, List
from datetime import datetime, timezone
import requests

from .config import CG_BASE, GT_BASE, PANCAKE_INFO_BASE, DEFAULT_HEADERS, WBNB_BSC, IS_DEV
from .registry import LST_REGISTRY_BSC

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
    if IS_DEV:
        return {
            "symbol": "BNB",
            "name": "BNB (testnet reference)",
            "coingecko_id": None,
            "price_usd": None,
            "change_24h_pct": None,
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "source": "dev",
            "sources": [],
        }
        
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
    if IS_DEV:
        enriched = []
        now_iso = datetime.now(timezone.utc).isoformat()
        for t in LST_REGISTRY_BSC:
            enriched.append(
                {
                    "symbol": t["symbol"],
                    "name": t["name"],
                    "address": t["address"],
                    "project": t["project"],
                    "price_usd": None,
                    "price_bnb": None,
                    "peg_ratio": None,
                    "change_24h_pct": None,
                    "sources": t.get("sources", []),
                    "last_updated": now_iso,
                }
            )
        return enriched
    
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
