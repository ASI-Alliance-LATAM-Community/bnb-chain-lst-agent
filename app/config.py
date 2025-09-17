import os
from dotenv import load_dotenv
from uagents_core.storage import ExternalStorage

load_dotenv()

# === ASI1 Config ===

ASI1_API_KEY = os.getenv("ASI1_API_KEY")
ASI1_BASE_URL = "https://api.asi1.ai/v1"
ASI1_HEADERS = {
    "Authorization": f"Bearer {ASI1_API_KEY}" if ASI1_API_KEY else "",
    "Content-Type": "application/json",
}

# === BNB Chain Config ===

BSC_RPC_URL = os.getenv("BSC_RPC_URL")
CHAIN_ID = 56

# === Agentverse Config ===

AGENTVERSE_API_KEY = os.getenv("AGENTVERSE_API_KEY")
AGENTVERSE_URL = os.getenv("AGENTVERSE_URL", "https://agentverse.ai").rstrip("/")
STORAGE_URL = f"{AGENTVERSE_URL}/v1/storage"

external_storage = (
    ExternalStorage(api_token=AGENTVERSE_API_KEY, storage_url=STORAGE_URL)
    if AGENTVERSE_API_KEY
    else None
)

# === Sanity checks (fail fast) ===

if not ASI1_API_KEY:
    raise RuntimeError("ASI1_API_KEY not set. Add it to your environment or .env")
if not BSC_RPC_URL:
    raise RuntimeError("BSC_RPC_URL not set. Add it to your environment or .env")

# === Coingecko Config ===

GT_BASE = "https://api.geckoterminal.com/api/v2"
CG_BASE = "https://api.coingecko.com/api/v3"

# === Binance config ===

BINANCE_BASE = "https://api.binance.com"

# === PANCAKE Swap Config ===

PANCAKE_INFO_BASE = "https://api.pancakeswap.info/api/v2"
PANCAKE_SWAP_BASE = "https://pancakeswap.finance/swap"
ROUTER_V2 = "0x10ED43C718714eb63d5aA57B78B54704E256024E"
WBNB_BSC = "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c".lower()

# === General Config ===

DEFAULT_HEADERS = {
    "Accept": "application/json",
    "User-Agent": "bnb-chain-lst-agent/1.0 (+https://example.com)",
}
