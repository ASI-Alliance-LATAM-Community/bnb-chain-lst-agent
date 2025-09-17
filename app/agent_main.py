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
from .storage import upload_png_to_storage


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
                "You can generate EIP-681 QR codes for on-chain actions on BNB Chain. "
                "When the user asks for LST list or prices, call the function list_lst_tokens. "
                "When the user asks for BNB price or BNB info, call the function get_bnb_info. "
                "When the user wants to buy an LST, call the function create_buy_lst_tx_qr. "
                "When the user asks to approve a token allowance, call the function create_approve_qr "
                "with the token address and optional amount. If amount is omitted, use unlimited allowance. "
                "Before proposing a swap transaction, always simulate it via eth_call and report pass/fail. "
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
        tool_calls = model_msg.get("tool_calls", []) or []

        if not tool_calls:
            return "Sorry, I couldn't find any action to execute for your query. Please, try again or adjust your question."

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

            if func_name in {
                "create_buy_lst_tx_qr",
                "create_approve_qr",
            } and tool_result.get("ok"):
                if func_name == "create_buy_lst_tx_qr":
                    tok = tool_result["token"]["symbol"]
                    amt = tool_result["amount_bnb"]
                    slip = tool_result["slippage_bps"]
                    slip_reason = tool_result.get("slippage_reason", "default 1.0%")
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
                        
                    gas_limit = tool_result.get("gas_limit")
                    gas_price = tool_result.get("gas_price")
                    gas_error = tool_result.get("gas_error")

                    gas_line = "**Gas:** "
                    gas_line += f"limit `{gas_limit}`" if gas_limit is not None else "limit `n/a`"
                    if gas_price is not None:
                        gas_line += f", price `{gas_price}` wei"
                    if gas_error:
                        gas_line += f" _(estimation note: {gas_error})_"

                    text = (
                        f"I generated a raw swap transaction for **{amt} BNB → {tok}**.\n\n"
                        f"{sim_line}\n\n"
                        f"**Slippage:** {slip/100:.2f}% — _{slip_reason}_\n"
                        f"{gas_line}\n" 
                        f"**Router:** `0x10ED43C718714eb63d5aA57B78B54704E256024E`\n"
                        f"**URI (EIP-681):** `{uri}`\n"
                        f"Scan the QR below to open **Confirm Transaction** in your wallet."
                    )
                else:
                    token_addr = tool_result["token"]
                    spender = tool_result["spender"]
                    amt_raw = tool_result["amount_uint256"]
                    uri = tool_result["uri"]
                    text = (
                        f"Generated an **approve()** transaction QR.\n\n"
                        f"**Token:** `{token_addr}`\n"
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
                        "name": "qr.png",
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
                        asset_id, asset_uri, err = upload_png_to_storage(
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
                                + "\n\nI couldn’t attach the QR image due to a storage error."
                            )
                            await ctx.send(sender, _text_msg(fallback_text))
                    else:
                        await ctx.send(sender, _text_msg(result["text"]))
                else:
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
