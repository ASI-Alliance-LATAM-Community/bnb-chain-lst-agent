import json
import requests
from uuid import uuid4
from datetime import datetime, timezone

from uagents_core.contrib.protocols.chat import (
    chat_protocol_spec,
    ChatMessage,
    ChatAcknowledgement,
    TextContent,
    StartSessionContent,
)
from uagents import Agent, Context, Protocol
from .config import ASI1_BASE_URL, ASI1_HEADERS, IS_DEV, CHAIN_ID, BSC_RPC_URL, GAS_BUDGET_MULTIPLIER, MIN_SWAP_VALUE_WEI
from .registry import LST_REGISTRY_BSC
from .tools import tools_schema, dispatch_tool
from .settlement import settlement_tick
from .rpc import rpc

def _text_msg(text: str) -> ChatMessage:
    return ChatMessage(
        timestamp=datetime.now(timezone.utc),
        msg_id=uuid4(),
        content=[TextContent(type="text", text=text)],
    )

def _wei_to_bnb(wei: int) -> float:
    return wei / 10**18

def _fmt_bnb(wei: int) -> str:
    return f"{_wei_to_bnb(wei):.6f}"

async def process_query(query: str, ctx: Context):
    try:
        user_message = {"role": "user", "content": query}
        system_message = {
            "role": "system",
            "content": (
                "You are an AI assistant called BNB-chain-LST-Agent. "
                f"Network mode: {'DEV (BSC Testnet)' if IS_DEV else 'PROD (BSC Mainnet)'}; chainId={CHAIN_ID}. "
                "You are a BNB-chain liquid staking expert. "
                "You generate EIP-681 pay URIs (no QR images) that open a 'Send BNB' screen in wallets. "
                "Tool usage:\n"
                "• When the user asks for LST list or prices, call the function list_lst_tokens.\n"
                "• When the user asks for BNB price or BNB info, call the function get_bnb_info.\n"
                "• When the user wants to buy an LST (or asks for a pay link that lets them send BNB), call the function create_managed_buy with symbol_or_address and recipient_address (optional slippage_bps).\n"
                "Behavior:\n"
                "• After creating a managed pay link, instruct the user to send any BNB amount (including gas) to the provided order address; explain the agent will swap BNB→LST on PancakeSwap v2 and deliver tokens to the recipient.\n"
                "• If the recipient address is missing, ask for it. If the token symbol is unknown, show the supported list.\n"
                "• Do not call tools that are not present in tools_schema.\n"
                "Here is the list of known LST tokens on BNB chain:\n"
                f"{LST_REGISTRY_BSC}"
            ),
        }

        payload = {
            "model": "asi1-mini",
            "messages": [system_message, user_message],
            "tools": tools_schema,
            "tool_choice": "auto",
            "temperature": 0.2,
            "max_tokens": 4096,
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
        tool_calls = model_msg.get("tool_calls") or []

        if not tool_calls:
            return (
                "Sorry, I couldn't find any action to execute for your query. "
                "Please try again, e.g.: 'Managed buy for BNBx → <your address>'."
            )

        for tc in tool_calls:
            func_name = tc["function"]["name"]
            try:
                args = json.loads(tc["function"].get("arguments") or "{}")
            except Exception:
                args = {}

            tool_result = dispatch_tool(func_name, args, ctx)

            messages_history.append(
                {
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "name": func_name,
                    "content": json.dumps(tool_result),
                }
            )

            if func_name == "create_managed_buy" and tool_result.get("ok"):
                tok = args.get("symbol_or_address", "LST")
                recv = tool_result.get("recv_addr")
                sbps = tool_result.get("slippage_bps")
                reason = tool_result.get("slippage_reason", "")
                uri = tool_result.get("uri", "")
                
                try:
                    gp = rpc("eth_gasPrice", [])
                    if "error" in gp:
                        raise RuntimeError(gp["error"].get("message", "gasPrice error"))
                    gas_price = int(gp["result"], 16)  # wei
                except Exception:
                    gas_price = 1_000_000_000
                

                gas_limit_guess = 160_000 
                est_gas_cost_wei = int(gas_limit_guess * gas_price * float(GAS_BUDGET_MULTIPLIER))
                min_required_wei = max(int(MIN_SWAP_VALUE_WEI), est_gas_cost_wei)
                
                text = (
                    f"🧾 **Managed order created** for **{tok}**\n\n"
                    f"**Send BNB to:** `{recv}`\n\n\n"
                    f"**Minimum to send:** ~{_fmt_bnb(min_required_wei)} BNB \n"
                    f"(includes est. gas @ ~{gas_limit_guess} gas × {gas_price/1e9:.2f} gwei × {GAS_BUDGET_MULTIPLIER}×)\n"
                    f"**How much?** Any amount (includes gas)\n"
                    f"**Slippage:** { (sbps or 0) / 100:.2f}% — _{reason}_\n\n"
                    f"**Pay URI (EIP-681):** `{uri}`\n\n\n"
                    f"Once your BNB arrives, I’ll swap BNB→{tok} on Pancake v2 and send the tokens to your address (chainId {CHAIN_ID})."
                )
                return text

            if not tool_result.get("ok"):
                err = tool_result.get("error", "Unknown error")
                return f"Tool `{func_name}` failed: {err}"

        final = requests.post(
            f"{ASI1_BASE_URL}/chat/completions",
            headers=ASI1_HEADERS,
            json={
                "model": "asi1-mini",
                "messages": messages_history,
                "temperature": 0.2,
                "max_tokens": 4096,
            },
            timeout=60,
        )
        final.raise_for_status()
        return final.json()["choices"][0]["message"]["content"]

    except Exception as e:
        ctx.logger.error(f"Error processing query: {e}")
        return f"An error occurred: {e}"


agent = Agent(name="bnb-chain-lst-agent", port=8001, mailbox=True)
chat_proto = Protocol(spec=chat_protocol_spec)


@agent.on_event("startup")
async def _startup(ctx: Context):
    ctx.logger.info(
        f"🚀 Starting in {'DEV (testnet)' if IS_DEV else 'PROD (mainnet)'} mode | chainId={CHAIN_ID}"
    )
    ctx.logger.info(f"RPC: {BSC_RPC_URL}")


@agent.on_interval(period=6.0)
async def _settle(ctx: Context):
    await settlement_tick(ctx)


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

                response_text = (
                    result if isinstance(result, str) else json.dumps(result)
                )
                await ctx.send(sender, _text_msg(response_text))
            else:
                ctx.logger.info(f"Got unexpected content from {sender}")
    except Exception as e:
        ctx.logger.error(f"Error handling chat message: {str(e)}")
        await ctx.send(sender, _text_msg(f"An error occurred: {str(e)}"))


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
