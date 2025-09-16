import requests
from uagents import Agent, Context, Protocol
from typing import List, Dict, Any
# from web3 import Web3
# from web3.middleware import geth_poa_middleware
from datetime import datetime, timezone
from uuid import uuid4
from uagents_core.contrib.protocols.chat import (
    chat_protocol_spec,
    ChatMessage,
    ChatAcknowledgement,
    TextContent,
    StartSessionContent,
)
import os
from dotenv import load_dotenv

load_dotenv()

# ASI1 Config

ASI1_API_KEY = os.getenv("ASI1_API_KEY")
ASI1_BASE_URL = "https://api.asi1.ai/v1"
ASI1_HEADERS = {
    "Authorization": f"Bearer {ASI1_API_KEY}",
    "Content-Type": "application/json",
}

# BNB Chain Config

BSC_RPC_URL = os.getenv("BSC_RPC_URL")

if not ASI1_API_KEY:
    raise RuntimeError("ASI1_API_KEY not set. Add it to your environment or .env")
if not BSC_RPC_URL:
    raise RuntimeError("BSC_RPC_URL not set. Add it to your environment or .env")



# web3 = Web3(Web3.HTTPProvider(BSC_RPC_URL))
# web3.middleware_onion.inject(geth_poa_middleware, layer=0)

LST_REGISTRY_BSC: List[Dict[str, Any]] = [
    {
        "symbol": "BNBx",
        "name": "Stader BNBx",
        "address": "0x1bdd3Cf7F79cfB8EdbB955f20ad99211551BA275",
        "project": "Stader",
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
        "sources": [
            "https://www.coingecko.com/en/coins/pstake-staked-bnb",
            "https://bscscan.com/token/0xc2e9d07f66a89c44062459a47a0d2dc038e4fb16",
        ],
    },
    {
        "symbol": "SNBNB",
        "name": "Synclub Staked BNB",
        "address": "0xb0b84d294e0c75a6abe60171b70edeb2efd14a1b",
        "project": "Synclub",
        "sources": [
            "https://apespace.io/bsc/0xb0b84d294e0c75a6abe60171b70edeb2efd14a1b",
            "https://bscscan.com/token/0xb0b84d294e0c75a6abe60171b70edeb2efd14a1b",
        ],
    },
]

async def process_query(query: str, ctx: Context) -> str:
    try:
        initial_message = {"role": "user", "content": query}
        system_message = {
            "role": "system",
            "content": (
                "You are a BNB-chain liquid staking expert. "
                "Here is the list of known LST tokens on BNB chain:\n"
                f"{LST_REGISTRY_BSC}"
            ),
        }
        
        payload = {
            "model": "asi1-mini",
            "messages": [system_message, initial_message],
            # "tools": tools,
            "temperature": 0.7,
            "max_tokens": 4096,
        }

        resp = requests.post(
            f"{ASI1_BASE_URL}/chat/completions",
            headers=ASI1_HEADERS,
            json=payload,
        )
        resp.raise_for_status()
        response_json = resp.json()

        model_msg = response_json["choices"][0]["message"]
        # tool_calls = model_msg.get("tool_calls", [])
        messages_history = [system_message, initial_message, model_msg]

        # if not tool_calls:
        #     return "Sorry, I couldn't find any action to execute for your query. Please, try again or adjust your question."

        # for tool_call in tool_calls:
        #     func_name = tool_call["function"]["name"]
        #     arguments = json.loads(tool_call["function"]["arguments"] or "{}")
        #     tool_call_id = tool_call["id"]

        #     try:
        #         if func_name in CANISTER_TOOL_NAMES:
        #             ctx.logger.info(f"[CALL] Calling CANISTER endpoint: {func_name} with args: {arguments}")
        #             result = await call_canister_endpoint(func_name, arguments, ctx)
        #         elif func_name in ICP_TOOL_NAMES:
        #             ctx.logger.info(f"[CALL] Calling ICP endpoint: {func_name} with args: {arguments}")
        #             result = await call_icp_endpoint(func_name, arguments, ctx)
        #             ctx.logger.info(f"[RESULT] {func_name} result: {result}")
        #         else:
        #             raise ValueError(f"Unsupported tool: {func_name}")

        #         content_to_send = json.dumps(result)

        #     except Exception as e:
        #         ctx.logger.error(f"Tool execution failed for {func_name}: {e}")
        #         content_to_send = json.dumps(
        #             {"error": format_error_response(e), "status": "failed", "tool": func_name}
        #         )

        #     messages_history.append(
        #         {"role": "tool", "tool_call_id": tool_call_id, "content": content_to_send}
        #     )

        # final_payload = {
        #     "model": "asi1-mini",
        #     "messages": messages_history,
        #     "temperature": 0.7,
        #     "max_tokens": 4096,
        # }
        # final_response = requests.post(
        #     f"{ASI1_BASE_URL}/chat/completions",
        #     headers=ASI1_HEADERS,
        #     json=final_payload,
        # )
        # final_response.raise_for_status()
        # return model_msg.json()["choices"][0]["message"]["content"]
        return model_msg["content"]

    except Exception as e:
        ctx.logger.error(f"Error processing query: {e}")
        return f"An error occurred: {e}"

# Agent and Protocol Setup

agent = Agent(
    name="bnb-chain-lst-agent", 
    port=8001, 
    mailbox=True
)
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
                response_text = await process_query(item.text, ctx)
                ctx.logger.info(f"Response text: {response_text}")
                response = ChatMessage(
                    timestamp=datetime.now(timezone.utc),
                    msg_id=uuid4(),
                    content=[TextContent(type="text", text=response_text)],
                )
                await ctx.send(sender, response)
            else:
                ctx.logger.info(f"Got unexpected content from {sender}")
    except Exception as e:
        ctx.logger.error(f"Error handling chat message: {str(e)}")
        error_response = ChatMessage(
            timestamp=datetime.now(timezone.utc),
            msg_id=uuid4(),
            content=[TextContent(type="text", text=f"An error occurred: {str(e)}")],
        )
        await ctx.send(sender, error_response)


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