from typing import List, Dict, Any

# Known LST tokens on BNB Chain
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

# DEV Environment (BNB Testnet) - using same addresses for simplicity

LST_REGISTRY_BSC_DEV = [
    {
        "symbol": "CAKE",
        "name": "PancakeSwap Token (Testnet)",
        "address": "0xFa60D973F7642B748046464e165A65B7323b0DEE",
        "project": "Pancake (testnet)",
        "aliases": ["BNBx", "ANKRBNB", "STKBNB"],
    },
    {
        "symbol": "BUSD",
        "name": "BUSD (Testnet)",
        "address": "0xED24FC36d5Ee211Ea25A80239Fb8C4Cfd80f12Ee",
        "project": "Testnet",
        "aliases": [],
    },
]
