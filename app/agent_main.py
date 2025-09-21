import json
import base64
import requests
from uuid import uuid4
from datetime import datetime, timezone

from uagents_core.contrib.protocols.chat import (
    chat_protocol_spec,
    ChatMessage,
    ChatAcknowledgement,
    TextContent,
    StartSessionContent,
    ResourceContent,
    Resource,
)
from uagents import Agent, Context, Protocol
from uagents_core.storage import ExternalStorage
from .config import ASI1_BASE_URL, ASI1_HEADERS
from .registry import LST_REGISTRY_BSC
from .tools import tools_schema, dispatch_tool
from .settlement import settlement_tick


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


async def process_query(query: str, ctx: Context):
    try:
        user_message = {"role": "user", "content": query}
        system_message = {
            "role": "system",
            "content": (
                "You are an AI assistant called BNB-chain-LST-Agent. "
                "You are a BNB-chain liquid staking expert. "
                "You generate EIP-681 pay URIs (no QR images) that open a 'Send BNB' screen in wallets. "
                "Tool usage:\n"
                "• When the user asks for LST list or prices, call the function list_lst_tokens.\n"
                "• When the user asks for BNB price or BNB info, call the function get_bnb_info.\n"
                "• When the user wants to buy an LST (or asks for a pay link that lets them send BNB), call the function create_managed_buy.\n"
                "Behavior:\n"
                "• After creating a managed QR, instruct the user to send any BNB amount (including gas) to the provided order address; explain the agent will swap BNB→LST on PancakeSwap v2 and deliver tokens to the recipient on BNB Chain (chainId 56).\n"
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
        tool_calls = model_msg.get("tool_calls") or []

        if not tool_calls:
            return (
                "Sorry, I couldn't find any action to execute for your query. "
                "Please try again, e.g.: 'Managed buy QR for BNBx → <your address>'."
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
                text = (
                    f"🧾 **Managed order created** for **{tok}**\n\n"
                    f"**Send BNB to:** `{recv}`\n"
                    f"**How much?** Any amount (includes gas)\n"
                    f"**Slippage:** { (sbps or 0) / 100:.2f}% — _{reason}_\n"
                    f"**URI (EIP-681):** `{uri}`\n\n"
                    f"Send tokens straight to your address."
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
                "max_tokens": 2048,
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

                # result is now always text (str) or a JSON stringifiable object
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
