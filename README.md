<div align="center">

<img src="./bnb-chain-logo.png" alt="BNB DeFi Risk Shield Logo" width="200">

<p></p>

<h1>BNB Chain LST Agent</h1>

<p>
    <img src="https://img.shields.io/badge/innovationlab-3D8BD3" alt="innovationlab">
    <img src="https://img.shields.io/badge/asi-3D8BD3" alt="ASI">
</p>
</div>

Agent built with **FastAPI + uAgents + Web3** to perform *liquid staking* on **BNB Chain** in an extremely simple way, without long‑term custody of funds or user account creation.

## 🚀 What it does


1. **Lists available Liquid Staking Tokens (LST)** on BNB Chain (e.g. **Stader BNBx**, **pSTAKE stkBNB**).
2. User **creates an order** specifying provider and BNB amount to stake.
3. The agent responds with an **order ID** and a **unique deposit address**.
4. User **sends BNB** from their wallet to that deposit address.
5. The agent **automatically detects the deposit**, executes the **stake** on the chosen provider and **sends the LST directly to the address that sent the funds**.
6. User can **check the order status** and all on-chain transaction hashes.


No user accounts are created and no balances are stored. Each order is **self-contained**: ephemeral address → stake → send LST → done.

```json
[
{
"key": "stader",
"symbol": "BNBx",
"stake_contract": "0x..."
},
{
"key": "pstake",
"symbol": "stkBNB",
"stake_contract": "0x..."
}
]
```


### 2️⃣ Create a staking order
```
POST /orders
{
"provider": "stader",
"amount_bnb": 0.1
}
```
Response:
```json
{
"order_id": 1,
"deposit_address": "0xabc123..."
}
```
The user must send **exactly 0.1 BNB** from their wallet to `deposit_address`.


### 3️⃣ Check an order status
```
GET /orders/{order_id}
```
Sample response:
```json
{
"id": 1,
"provider": "stader",
"amount_bnb": 0.1,
"deposit_address": "0xabc123...",
"sender_address": "0xuserwallet...",
"status": "completed",
"tx_in_hash": "0xtxhashin...",
"tx_stake_hash": "0xtxhashstake...",
"tx_out_hash": "0xtxhashout..."
}
```
Possible status: `waiting_deposit` → `staking` → `completed` (or `failed`).


---


## 🛠️ Internal flow
- **Address per order:** Derived from `MASTER_MNEMONIC` using BIP-44. Each order has its own address and private key.
- **Deposit detection:** `monitor_loop` periodically queries BscScan API to check if BNB was received at the order address.
- **Automatic staking:** Once a deposit is detected, the agent calls the staking method of the chosen provider (`submit` for Stader, `deposit` for pSTAKE) from that address.
- **Sending LST:** After receiving the LST tokens (BNBx or stkBNB), the agent transfers them directly to the address that sent the BNB (`sender_address`).
- **Database:** SQLite (`orders.db`) stores the order history and transaction hashes.


---


## 🔒 Security
- **No long-term custody:** funds are immediately staked and LST are sent back to the user.
- **Secure HD seed:** only one mnemonic (`MASTER_MNEMONIC`) is used to derive ephemeral addresses.
- **Provider allowlist:** interacts only with contracts configured in `.env`.
- **Amount verification:** received amount must be >= 99.9% of the requested amount to be considered valid.


---


## 🗺️ Roadmap
- Add more LST providers and dynamic APR retrieval.
- Add **native unstake** mode (cooldown) in addition to instant exit.
- Push/webhook notifications when an order completes.
- Web dashboard to view orders in real time.


---


## 📜 License
MIT – Use at your own risk. Make sure you understand the risks of interacting with staking contracts on BNB Chain.