<div align="center">

<img src="./bnb-chain-logo.png" alt="BNB DeFi Risk Shield Logo" width="200">

<p></p>

<h1>BNB Chain LST Agent</h1>

<p>
    <img src="https://img.shields.io/badge/innovationlab-3D8BD3" alt="innovationlab">
    <img src="https://img.shields.io/badge/asi-3D8BD3" alt="ASI">
</p>
</div>



> **Hackathon Track:** *Unlocking Agent Intelligence on BNB Chain*
> **Goal:** Build an autonomous AI agent that performs on-chain actions using **Fetch.ai uAgents** + **ASI-1 Mini (Web3-native LLM)** on **BNB Chain**.

---

## ✨ What this agent does

**BNB-chain-LST-Agent** lets a user buy LSTs on BNB Chain by simply sending BNB to a one-time, agent-managed address:

* The agent creates a **per-order wallet** (ephemeral).
* User sends any BNB amount (including gas) to that unique address (via **EIP-681 pay URI**).
* The agent **swaps BNB → target LST** (via PancakeSwap v2) and sends tokens to the user’s address.
* Robust **settlement loop** handles gas estimation, simulation, execution, and errors.
* If a swap fails, the agent **never strands funds** — it enters a **refund flow** and attempts to **return BNB** safely to the user, retrying until successful.
* Supports **DEV / PROD network switch** (BNB Testnet vs Mainnet) via an env flag.
* **Market data built in:** the agent can report **BNB price** and **registered LST prices/info** using **CoinGecko** (and optional Binance spot as a source), with safe fallbacks.

This showcases:

* **Smart contract integration** (router calls, eth\_call simulations, gas estimation).
* **On-chain execution** (signed transactions, per-order wallets).
* **Autonomy & intelligence** (slippage autopilot, gas budgeting, safety fallbacks).
* **Agent+LLM orchestration** (ASI-1 Mini tools for listing tokens, prices, BNB info, and creating managed buys).

---

## 🧩 Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                      Chat / Agentverse UI                      │
│   User: “Buy BNBx to 0x… I’ll send BNB”                        │
└────────────────────────────────────────────────────────────────┘
                 │
                 ▼
        ASI-1 Mini (LLM, tools)
  ┌────────────────────────────────┐
  │ tools:                         │
  │  • list_lst_tokens             │
  │  • get_bnb_info                │
  │  • create_managed_buy          │
  └────────────────────────────────┘
                 │
                 ▼
        uAgents runtime (Python)
  ┌──────────────────────────────────────────────────────────────┐
  │ - Managed order store (ctx.storage JSON)                     │
  │ - Per-order wallet generation (eth_account)                  │
  │ - EIP-681 pay URI generation                                 │
  │ - Settlement loop (interval):                                │
  │     • detect funding                                         │
  │     • gas estimate + budget                                  │
  │     • simulate swap (eth_call)                               │
  │     • broadcast legacy tx                                    │
  │     • success → complete                                     │
  │     • failure → refund_pending → try refund                  │
  └──────────────────────────────────────────────────────────────┘
                 │
                 ▼
             BNB Chain RPC
     (Mainnet or Testnet based on ENV)
```

---

## 🧠 Key Behaviors

### Managed Buy Flow

`create_managed_buy` returns:

* `recv_addr` (unique order address)
* **Pay URI** `ethereum:<recv_addr>@<chainId>` (EIP-681)
* **Minimum BNB** suggested (gas-aware) to avoid “underfunded” orders

### Settlement Loop (every N seconds)

1. If **pending** and funded → simulate → estimate gas → **swap** → complete
2. On **revert/gas failure/insufficient funds** → **refund\_pending**, attempt refund to recipient; if not enough for gas, keep retrying later
3. Orders only leave the active set when **complete** or **refunded** (never stranded)

### State Machine

`pending` → `complete` or `refund_pending` → `refunded`

---

## 💹 Built-in Market Data (BNB & LST registry)

This agent includes **lightweight price tooling** accessible via the LLM tools:

### BNB Price (`get_bnb_info`)

* **Primary source:** **CoinGecko** `simple/price` for `binancecoin` (USD), with 24h change and timestamp.
* **Fallbacks:** **GeckoTerminal** (WBNB price) and **PancakeSwap Info** if CoinGecko is unavailable.
* **DEV mode:** returns a stub (no USD price) so you can test without hitting real price APIs.

> The repo also defines **`BINANCE_BASE`** and is ready to use **Binance public REST** (e.g., `BNBUSDT` spot) as an additional source if desired. Current default path prioritizes **CoinGecko** for convenience and rate-limit friendliness.

**Example (chat):**

```
What’s BNB price right now?
```

**Agent (tool-backed):**

```
BNB ≈ $XXX.XX (source: coingecko_id), 24h Δ: +Y.YY%
Last updated: 2025-09-22T…
```

### LST Registry Prices (`list_lst_tokens`)

* Maintains a curated registry of supported LSTs on BNB Chain.
* For tokens with a **CoinGecko ID**, fetches USD price + 24h change via CoinGecko.
* For tokens **without** a CoinGecko ID, fetches by **contract address** via **GeckoTerminal**.
* Computes **price in BNB** and a **peg ratio** (LST/BNB) using the current BNB/USD.
* Returns symbol, name, address, project, `price_usd`, `price_bnb`, `peg_ratio`, `change_24h_pct`, `sources`, `last_updated`.
* **DEV mode:** returns registry metadata with `None` prices—safe for testnet demos.

**Example (chat):**

```
List supported LSTs and prices
```

**Agent (tool-backed):**

```
- BNBx — $XXX.XX (~Y.YY BNB), 24h Δ +Z.ZZ%
  address: 0x1bdd…; project: Stader; last_updated: …
- ANKRBNB — …
- STKBNB — …
```

---

## 🚀 Getting Started

### Prerequisites

* Python 3.11+
* A BNB RPC endpoint (Mainnet and/or Testnet)
* Agentverse account (for registration/hosting)
* API key for **ASI-1 Mini** (ASI-1 endpoint used by tools)

### Install

```bash
git clone https://github.com/your-org/bnb-chain-lst-agent.git
cd bnb-chain-lst-agent
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Environment

Create `.env` in the project root:

```ini
# ASI:One API Key
ASI1_API_KEY=

# Agent’s internal key (never reuse for real funds)
AGENT_PRIV=

# BNB Chain wallet private key for the agent
AGENT_PRIV=

# DEV uses BSC Testnet; otherwise PROD uses mainnet
ENVIROMENT=

# Mainnet RPC
BSC_RPC_URL=

# Testnet RPC
BSC_RPC_URL_DEV=
```



### Run the agent locally

```bash
python -m app.agent_main
```

The agent will log the chain, RPC and start serving. Register/host it on **Agentverse** for hackathon compliance.

---

## 💬 Chat Commands & Examples

**Create a managed buy (LLM-tool path):**

```
Buy BNBx to 0xYourAddressHere — I’ll send BNB
```

Agent replies with:

* **Order ID**
* **Send BNB to:** per-order address
* **Minimum to send** (gas-aware, dynamic)
* **Pay URI:** `ethereum:<order-address>@<chainId>`

**Get BNB price:**

```
BNB price?
```

**List LSTs + prices:**

```
Show LST tokens and prices/info
```

**Check order status (optional custom command):**

```
/status <order_id>
```

Returns `status: pending | refund_pending | complete | refunded`, addresses and tx hash (if any).

---

## 🧪 DEV vs PROD

* `ENVIROMENT=DEV` → **BNB Testnet** (chainId `97`)

  * Registry maps mainnet symbols to test tokens (e.g., `CAKE` testnet) with aliases (`BNBx`, `ANKRBNB`, `STKBNB`) for smooth demos.
  * Price endpoints return **stubs** so you can test flows without live price queries.
* `ENVIROMENT=PROD` → **BNB Mainnet** (chainId `56`)

  * Uses mainnet LST registry and live price lookups.

Switch easily by toggling the env and setting the right RPC.

---

## 🔐 Security & Safety

* **Per-order wallets**: Funds are isolated per order; private keys are stored **locally** (JSON via `ctx.storage`), never shared.
* **Simulation first**: All swaps are `eth_call` simulated before broadcasting.
* **Gas budgeting**: Uses live gas price to reserve gas before deciding swap `amount_in`.
* **Refund guaranteed**: On any non-recoverable error, the agent attempts to **refund** BNB back to the recipient. If not enough for refund gas, it stays in `refund_pending` and keeps retrying (never dropped).
* **No QR images**: Uses EIP-681 pay URIs (more robust across wallets).

---

## 🛠️ Notable Modules

* `agent_main.py` — chat protocol, LLM tools, minimum-send guidance, `/status` (if enabled)
* `tools.py` — tool schema + dispatcher:
  `list_lst_tokens`, `get_bnb_info`, `create_managed_buy`
* `managed_buy.py` — creates per-order wallet and pay URI (EIP-681)
* `settlement.py` — periodic settlement & **refund** state machine; `_broadcast_legacy` signing/broadcast
* `prices.py` — **BNB price** (`get_bnb_info`) and **LST registry prices** (`list_lst_tokens`)

  * Sources: **CoinGecko** primary; **GeckoTerminal**/**Pancake Info** fallbacks
  * (Binance base URL defined for optional use)
* `rpc.py` — JSON-RPC helpers; `get_amount_out_min`, `simulate_swap`
* `tx_builders.py` — Pancake v2 `swapExactETHForTokens` calldata & EIP-681 helpers
* `orders_kv.py` — order storage (JSON via `ctx.storage`) with statuses: `pending / refund_pending / complete / refunded`
* `registry.py` / `registry_dev.py` — LST registry (mainnet/testnet)
* `config.py` — env wiring, chain IDs, RPC URLs, explorer link builders


## 📈 Example Flow (Testnet)

1. User: “**Buy BNBx** to `0x6FD7…533D` — I’ll send BNB.”
2. Agent:

   * Creates order `abcd1234…`
   * Returns `recv_addr`, **minimum BNB**, EIP-681 pay URI (`ethereum:<recv_addr>@97`)
3. User sends, e.g., `0.02 BNB` to `recv_addr`.
4. Settlement:

   * Detects funding
   * Simulates swap WBNB→token
   * Estimates gas, budgets fees, sets `amount_in`
   * Broadcasts swap (legacy tx)
   * On success → `complete`
   * On failure → `refund_pending`, attempts refund; if needed keeps retrying until success → `refunded`


## 🧪 Judging Criteria (how this project addresses them)

1. **Fetch.ai Tech Utilization**
   Uses uAgents, ctx.storage, Agentverse hosting; tool-driven LLM orchestration (ASI-1 Mini) for flexible, safe on-chain actions and market data retrieval.

2. **Technical Implementation**
   Clean separation of concerns; robust calldata building, simulation, gas estimation, and safe error/refund handling. Dev/Mainnet switch via env. Price tooling with multi-source fallbacks (CoinGecko primary; Binance optional; GeckoTerminal/Pancake Info fallback).

3. **Agent Autonomy & Intelligence**
   Auto-slippage based on liquidity/volatility, dynamic minimum-send, path simulation before tx, autonomous settlement loop and refund state machine.

4. **Impact & Use Case**
   Smooth user UX for buying LSTs; extensible to DEX trades, approvals, governance interactions, and wider DeFi automation. Built-in price insights for BNB and LST registry.


## 🗺️ Roadmap / Extensions

* Add token **allowance** flow (approve when needed)
* Multi-hop routes (WBNB → stable → LST) with on-chain routing oracle
* On-chain **governance voting** by agent policies
* Pluggable **price feeds** & risk checks (expand Binance usage by default)
* Optional **user notifications** (queued + retry) when relay stability allows

---

## ⚠️ Disclaimer

This project is for **hackathon/demo** purposes. Keys and endpoints in `.env` are sensitive — **never** commit or share them. Always test on **BNB Testnet** first. Use at your own risk.

---

## 📄 License

MIT