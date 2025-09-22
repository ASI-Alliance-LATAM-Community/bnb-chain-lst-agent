import os
from dotenv import load_dotenv
from uagents_core.storage import ExternalStorage

load_dotenv()

# === Environment Config ===

ENVIROMENT = (os.getenv("ENVIROMENT") or "").strip().upper()
IS_DEV = ENVIROMENT == "DEV"

# === ASI1 Config ===

ASI1_API_KEY = os.getenv("ASI1_API_KEY")
ASI1_BASE_URL = "https://api.asi1.ai/v1"
ASI1_HEADERS = {
    "Authorization": f"Bearer {ASI1_API_KEY}" if ASI1_API_KEY else "",
    "Content-Type": "application/json",
}

# === BNB Chain Config ===
BSC_RPC_URL = os.getenv("BSC_RPC_URL_DEV") if IS_DEV else os.getenv("BSC_RPC_URL")
CHAIN_ID = 97 if IS_DEV else 56

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

if IS_DEV:
    ROUTER_V2 = "0x9Ac64Cc6e4415144C455BD8E4837Fea55603e5c3"  # Pancake V2 router (testnet)
    WBNB_BSC = "0xae13d989dac2f0debff460ac112a837c89baa7cd".lower()  # WBNB (testnet)
else:
    ROUTER_V2 = "0x10ED43C718714eb63d5aA57B78B54704E256024E"  # Pancake V2 router (mainnet)
    WBNB_BSC = "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c".lower()  # WBNB (mainnet)

# === Agent Wallet Config ===

AGENT_PRIV = os.getenv("AGENT_PRIV")
if not AGENT_PRIV:
    raise RuntimeError("AGENT_PRIV not set. Add it to your environment or .env")

GAS_BUDGET_MULTIPLIER = float(os.getenv("GAS_BUDGET_MULTIPLIER", "1.2"))
MIN_SWAP_VALUE_WEI = int(os.getenv("MIN_SWAP_VALUE_WEI", str(200_000_000_000_000)))

# === General Config ===

DEFAULT_HEADERS = {
    "Accept": "application/json",
    "User-Agent": f"bnb-chain-lst-agent/1.0 ({'dev' if IS_DEV else 'prod'})",
}