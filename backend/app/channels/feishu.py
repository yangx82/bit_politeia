"""Feishu/Lark channel implementation using lark-oapi SDK with WebSocket long connection."""

import asyncio
import json
import threading
import logging
from collections import OrderedDict
from typing import Any

from ..bus.events import OutboundMessage
from ..bus.queue import MessageBus
from .base import BaseChannel

logger = logging.getLogger(__name__)

try:
    import lark_oapi as lark
    from lark_oapi.api.im.v1 import (
        CreateMessageRequest,
        CreateMessageRequestBody,
        CreateMessageReactionRequest,
        CreateMessageReactionRequestBody,
        CreateFileRequest,
        CreateFileRequestBody,
        CreateImageRequest,
        CreateImageRequestBody,
        GetMessageResourceRequest,
        Emoji,
        P2ImMessageReceiveV1,
    )
    FEISHU_AVAILABLE = True
except ImportError:
    FEISHU_AVAILABLE = False
    lark = None
    Emoji = None

# Message type display mapping
MSG_TYPE_MAP = {
    "image": "[image]",
    "audio": "[audio]",
    "file": "[file]",
    "sticker": "[sticker]",
}


class FeishuConfig:
    def __init__(self, app_id, app_secret, encrypt_key, verification_token):
        self.app_id = app_id
        self.app_secret = app_secret
        self.encrypt_key = encrypt_key
        self.verification_token = verification_token
        self.allow_from = []

class FeishuChannel(BaseChannel):
    """
    Feishu/Lark channel using WebSocket long connection.
    
    Uses WebSocket to receive events - no public IP or webhook required.
    
    Requires:
    - App ID and App Secret from Feishu Open Platform
    - Bot capability enabled
    - Event subscription enabled (im.message.receive_v1)
    """
    
    name = "feishu"
    
    def __init__(self, app_id: str, app_secret: str, bus: MessageBus, encrypt_key: str = None, verification_token: str = None):
        # Config object simulation
        config = FeishuConfig(app_id, app_secret, encrypt_key, verification_token)
        
        super().__init__(config, bus)
        self.config = config
        self._client: Any = None
        self._ws_client: Any = None
        self._ws_thread: threading.Thread | None = None
        self._processed_message_ids: OrderedDict[str, None] = OrderedDict()  # Ordered dedup cache
        self._loop: asyncio.AbstractEventLoop | None = None
    
    async def start(self) -> None:
        """Start the Feishu bot with WebSocket long connection."""
        if not FEISHU_AVAILABLE:
            logger.error("Feishu SDK not installed. Run: pip install lark-oapi")
            return
        
        if not self.config.app_id or not self.config.app_secret:
            logger.error("Feishu app_id and app_secret not configured")
            return
        
        self._running = True
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.warning("No running event loop found for Feishu channel.")
        
        # Create Lark client for sending messages
        self._client = lark.Client.builder() \
            .app_id(self.config.app_id) \
            .app_secret(self.config.app_secret) \
            .log_level(lark.LogLevel.INFO) \
            .build()
        
        # Create event handler (only register message receive, ignore other events)
        event_handler = lark.EventDispatcherHandler.builder(
            self.config.encrypt_key or "",
            self.config.verification_token or "",
        ).register_p2_im_message_receive_v1(
            self._on_message_sync
        ).build()
        
        # Create WebSocket client for long connection
        self._ws_client = lark.ws.Client(
            self.config.app_id,
            self.config.app_secret,
            event_handler=event_handler,
            log_level=lark.LogLevel.INFO
        )
        
        # Start WebSocket client in a separate thread
        def run_ws():
            try:
                self._ws_client.start()
            except Exception as e:
                logger.error(f"Feishu WebSocket error: {e}")
        
        self._ws_thread = threading.Thread(target=run_ws, daemon=True)
        self._ws_thread.start()
        
        logger.info("Feishu bot started with WebSocket long connection")
        
        # Keep running until stopped
        while self._running:
            await asyncio.sleep(1)
    
    async def stop(self) -> None:
        """Stop the Feishu bot."""
        self._running = False
        if self._ws_client:
            # lark-oapi doesn't seem to expose a clean stop for WS client in all versions, 
            # but usually it runs in a loop.
            # We just stop our own loop and let the thread die or rely on app shutdown.
            pass
        logger.info("Feishu bot stopped")
    
    def _add_reaction_sync(self, message_id: str, emoji_type: str) -> None:
        """Sync helper for adding reaction (runs in thread pool)."""
        try:
            request = CreateMessageReactionRequest.builder() \
                .message_id(message_id) \
                .request_body(
                    CreateMessageReactionRequestBody.builder()
                    .reaction_type(Emoji.builder().emoji_type(emoji_type).build())
                    .build()
                ).build()
            
            response = self._client.im.v1.message_reaction.create(request)
            
            if not response.success():
                logger.warning(f"Failed to add reaction: code={response.code}, msg={response.msg}")
            else:
                logger.debug(f"Added {emoji_type} reaction to message {message_id}")
        except Exception as e:
            logger.warning(f"Error adding reaction: {e}")

    async def _add_reaction(self, message_id: str, emoji_type: str = "THUMBSUP") -> None:
        """
        Add a reaction emoji to a message (non-blocking).
        """
        if not self._client or not Emoji:
            return
        
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._add_reaction_sync, message_id, emoji_type)
    
    def _upload_file(self, file_path: str, file_type: str) -> str:
        """Upload a file to Feishu and return its file_key or image_key. Runs synchronously."""
        import os
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
            
        file_name = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)
        
        with open(file_path, "rb") as f:
            if file_type == "image":
                request = CreateImageRequest.builder() \
                    .request_body(CreateImageRequestBody.builder()
                        .image_type("message")
                        .image(f)
                        .build()) \
                    .build()
                response = self._client.im.v1.image.create(request)
                if not response.success():
                    raise Exception(f"Image upload failed: {response.code} {response.msg}")
                return response.data.image_key
            else:
                # Default to file
                request = CreateFileRequest.builder() \
                    .request_body(CreateFileRequestBody.builder()
                        .file_type("stream")
                        .file_name(file_name)
                        .duration(0)
                        .file(f)
                        .build()) \
                    .build()
                response = self._client.im.v1.file.create(request)
                if not response.success():
                    raise Exception(f"File upload failed: {response.code} {response.msg}")
                return response.data.file_key

    async def send(self, msg: OutboundMessage) -> None:
        """Send a message and optional files through Feishu."""
        if not self._client:
            logger.warning("Feishu client not initialized")
            return
        
        try:
            if msg.session_id.startswith("oc_"):
                receive_id_type = "chat_id"
            else:
                receive_id_type = "open_id"
            
            # 1. Send text content if present
            if msg.content or not msg.media:
                content = json.dumps({"text": msg.content})
                request = CreateMessageRequest.builder() \
                    .receive_id_type(receive_id_type) \
                    .request_body(
                        CreateMessageRequestBody.builder()
                        .receive_id(msg.session_id)
                        .msg_type("text")
                        .content(content)
                        .build()
                    ).build()
                
                response = self._client.im.v1.message.create(request)
                if not response.success():
                    logger.error(f"Failed to send Feishu text: code={response.code}, msg={response.msg}")
            
            # 2. Send media files
            if msg.media:
                loop = asyncio.get_running_loop()
                for item in msg.media:
                    if isinstance(item, dict):
                        file_path = item.get("path")
                        raw_type = item.get("type", "file")
                        
                        # Feishu differentiates image and file
                        file_type = "image" if raw_type in ["image", "photo"] else "file"
                        
                        try:
                            # Run upload in thread pool
                            media_key = await loop.run_in_executor(
                                None, self._upload_file, file_path, file_type
                            )
                            
                            logger.info(f"Feishu uploaded {file_type}, key={media_key}")
                            
                            # Build message content based on type
                            if file_type == "image":
                                media_content = json.dumps({"image_key": media_key})
                            else:
                                media_content = json.dumps({"file_key": media_key})
                                
                            media_request = CreateMessageRequest.builder() \
                                .receive_id_type(receive_id_type) \
                                .request_body(
                                    CreateMessageRequestBody.builder()
                                    .receive_id(msg.session_id)
                                    .msg_type(file_type)
                                    .content(media_content)
                                    .build()
                                ).build()
                                
                            media_resp = self._client.im.v1.message.create(media_request)
                            if not media_resp.success():
                                logger.error(f"Failed to send Feishu media: code={media_resp.code}, msg={media_resp.msg}")
                                
                        except Exception as upload_err:
                            logger.error(f"Failed to upload/send media {file_path}: {upload_err}")
                
        except Exception as e:
            logger.error(f"Error sending Feishu message: {e}")
    
    def _on_message_sync(self, data: "P2ImMessageReceiveV1") -> None:
        """
        Sync handler for incoming messages (called from WebSocket thread).
        Schedules async handling in the main event loop.
        """
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self._on_message(data), self._loop)
        else:
            logger.warning("Main event loop not running, cannot handle Feishu message")
    
    def _download_feishu_file(self, message_id: str, file_key: str, file_type: str, file_name: str) -> str:
        """Download a file from Feishu and return local path. Runs synchronously."""
        import os
        from pathlib import Path
        
        request = GetMessageResourceRequest.builder() \
            .message_id(message_id) \
            .file_key(file_key) \
            .type(file_type) \
            .build()
            
        response = self._client.im.v1.message_resource.get(request)
        if not response.success():
            raise Exception(f"Failed to get Feishu resource: {response.code} {response.msg}")
            
        download_dir = Path("data/downloads")
        download_dir.mkdir(parents=True, exist_ok=True)
        
        file_path = download_dir / f"fs_{message_id}_{file_name}"
        
        with open(file_path, "wb") as f:
            f.write(response.file)
            
        return str(file_path.absolute())

    async def _on_message(self, data: "P2ImMessageReceiveV1") -> None:
        """Handle incoming message from Feishu."""
        try:
            event = data.event
            message = event.message
            sender = event.sender
            
            # Deduplication check
            message_id = message.message_id
            if message_id in self._processed_message_ids:
                return
            self._processed_message_ids[message_id] = None
            
            # Trim cache: keep most recent 500 when exceeds 1000
            while len(self._processed_message_ids) > 1000:
                self._processed_message_ids.popitem(last=False)
            
            # Skip bot messages
            sender_type = sender.sender_type
            if sender_type == "bot":
                return
            
            sender_id = sender.sender_id.open_id if sender.sender_id else "unknown"
            session_id = message.chat_id
            chat_type = message.chat_type  # "p2p" or "group"
            msg_type = message.message_type
            
            # Add reaction to indicate "seen"
            await self._add_reaction(message_id, "THUMBSUP")
            
            # Parse message content
            content = ""
            media_items = []
            
            if msg_type == "text":
                try:
                    content = json.loads(message.content).get("text", "")
                except json.JSONDecodeError:
                    content = message.content or ""
            else:
                try:
                    parsed_content = json.loads(message.content)
                    file_key = parsed_content.get("file_key") or parsed_content.get("image_key")
                    
                    if file_key:
                        file_name = parsed_content.get("file_name", f"{file_key}.file")
                        resource_type = "image" if msg_type == "image" else "file"
                        
                        loop = asyncio.get_running_loop()
                        file_path = await loop.run_in_executor(
                            None, self._download_feishu_file, message_id, file_key, resource_type, file_name
                        )
                        
                        content = f"[System] User sent a {resource_type}: {file_name}"
                        media_items.append({
                            "type": "image" if resource_type == "image" else "file",
                            "path": file_path,
                            "name": file_name
                        })
                        logger.info(f"Downloaded Feishu {resource_type}: {file_path}")
                    else:
                        content = MSG_TYPE_MAP.get(msg_type, f"[{msg_type}]")
                except Exception as e:
                    logger.error(f"Failed to process Feishu media {msg_type}: {e}")
                    content = f"[System] User attempted to send a {msg_type}, but processing failed."

            if not content and not media_items:
                return
            
            # Forward to message bus
            reply_to = session_id 
            
            logger.info(f"Received Feishu message from {sender_id}: {content[:30]}...")
            
            await self._handle_message(
                sender_id=sender_id,
                session_id=session_id,
                content=content,
                media=media_items, # Pass media up to the base class handler
                metadata={
                    "message_id": message_id,
                    "chat_type": chat_type,
                    "msg_type": msg_type,
                    "username": sender.sender_id.user_id # No username in public event usually, just IDs
                }
            )
            
        except Exception as e:
            logger.error(f"Error processing Feishu message: {e}")
