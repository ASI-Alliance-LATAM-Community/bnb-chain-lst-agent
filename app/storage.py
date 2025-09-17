from typing import Tuple, Optional
import base64
from uuid import uuid4
from uagents import Context

from .config import external_storage


def upload_png_to_storage(
    ctx: Context, sender: str, png_bytes: bytes, mime: str = "image/png"
):
    if not external_storage:
        ctx.logger.error(
            "External storage not configured (AGENTVERSE_API_KEY or URL missing)."
        )
        return None, None, "storage_not_configured"
    asset_name = f"qr_{uuid4().hex}.png"
    try:
        asset_id = external_storage.create_asset(
            name=asset_name, content=png_bytes, mime_type=mime
        )
    except RuntimeError as err:
        ctx.logger.error(f"Asset creation failed: {err}")
        return None, None, f"create_failed:{err}"
    try:
        external_storage.set_permissions(asset_id=asset_id, agent_address=sender)
    except Exception as err:
        ctx.logger.error(f"set_permissions failed (non-fatal): {err}")
    asset_uri = f"agent-storage://{external_storage.storage_url}/{asset_id}"
    return asset_id, asset_uri, None
