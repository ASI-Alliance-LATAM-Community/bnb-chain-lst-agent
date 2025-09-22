from typing import Dict, Any
import json
import requests
from eth_utils import to_checksum_address

from .config import GT_BASE, DEFAULT_HEADERS, WBNB_BSC, IS_DEV

def fetch_pool_stats_bsc(token_addr: str) -> Dict[str, Any]:
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

        chosen = None
        for it in included:
            if it.get("type") != "pool":
                continue
            attrs = it.get("attributes", {}) or {}
            txt = json.dumps(attrs).lower()
            if WBNB_BSC in txt:
                chosen = attrs
                break
            if chosen is None:
                chosen = attrs

        if not chosen:
            return {}

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


def auto_slippage_bps(token_addr: str) -> tuple[int, str]:
    """
    Decide slippage (in bps) based on pool liquidity and 24h price movement.
    Policy:
      - default 1.0% (100 bps)
      - widen to 1.5–2.0% if pool is shallow or 24h move is large
      - tighten to 0.5% on deep + calm pools
    """
    if IS_DEV:
        return 100, "dev environment → using default 1.0%"
    
    DEEP_USD = 2_000_000  # ≥ $2M considered deep
    SHALLOW_USD = 200_000  # < $200k considered shallow
    VERY_SHALLOW_USD = 50_000  # < $50k very shallow
    LOW_VOL = 2.0  # ≤ 2% 24h move
    HIGH_VOL = 5.0  # ≥ 5% 24h move
    VERY_HIGH_VOL = 10.0  # ≥ 10% 24h move

    stats = fetch_pool_stats_bsc(token_addr)
    liq = stats.get("liquidity_usd")
    vol = abs(stats.get("price_change_24h") or 0.0)

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
                slippage = 100
                reason = f"moderate liquidity (~${liq:,.0f}) and 24h move {vol:.2f}% → using 1.0%"
        else:
            slippage = 100
            reason = "couldn’t fetch pool stats → using default 1.0%"
    except Exception as e:
        slippage = 100
        reason = f"autopilot error ({e}) → using default 1.0%"

    return slippage, reason
