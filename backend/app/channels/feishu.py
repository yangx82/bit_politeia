"""Feishu/Lark channel implementation using lark-oapi SDK with WebSocket long connection."""

import asyncio
import json
import logging
import multiprocessing
import os
import sys
import threading
from collections import OrderedDict
from typing import Any

from ..bus.events import OutboundMessage
from ..bus.queue import MessageBus
from .base import BaseChannel

logger = logging.getLogger(__name__)


def _feishu_ws_worker(app_id: str, app_secret: str, encrypt_key: str, verification_token: str, queue: multiprocessing.Queue):
    """
    独立的飞书 WebSocket 工作进程。
    避免与主进程的事件循环冲突。
    """
    import lark_oapi as lark
    import time
    
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s:    %(name)s - %(message)s"
    )
    ws_logger = logging.getLogger("feishu_ws")
    
    reconnect_delay = 5
    max_reconnect_delay = 60
    max_attempts = 10
    attempts = 0
    
    # 创建事件处理器
    event_handler = (
        lark.EventDispatcherHandler.builder(
            encrypt_key or "",
            verification_token or "",
        )
        .register_p2_im_message_receive_v1(lambda data: _handle_message_in_worker(data, queue))
        .register_p2_im_message_message_read_v1(lambda data: ws_logger.debug(f"Message read: {data}"))
        .build()
    )
    
    # 创建 WebSocket 客户端
    ws_client = lark.ws.Client(
        app_id,
        app_secret,
        event_handler=event_handler,
        log_level=lark.LogLevel.INFO,
    )
    
    ws_logger.info(f"Feishu WebSocket worker started (PID: {os.getpid()})")
    
    while attempts < max_attempts:
        try:
            ws_logger.info(f"Feishu WebSocket connecting (attempt {attempts + 1})")
            ws_client.start()
            # 如果 start() 返回，说明连接断开
            attempts += 1
            ws_logger.warning(f"Feishu WebSocket disconnected, reconnecting in {reconnect_delay}s...")
        except Exception as e:
            attempts += 1
            ws_logger.error(f"Feishu WebSocket error (attempt {attempts}): {e}")
        
        if attempts >= max_attempts:
            break
            
        time.sleep(reconnect_delay)
        reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)
    
    ws_logger.error(f"Feishu WebSocket max reconnect attempts ({max_attempts}) reached, worker exiting")


def _handle_message_in_worker(data, queue: multiprocessing.Queue):
    """在工作进程中处理收到的消息，转发到主进程"""
    try:
        import pickle
        # 将消息序列化后放入队列
        queue.put(("message", data))
    except Exception as e:
        logging.getLogger("feishu_ws").error(f"Failed to queue message: {e}")

try:
    import lark_oapi as lark
    from lark_oapi.api.im.v1 import (
        CreateFileRequest,
        CreateFileRequestBody,
        CreateImageRequest,
        CreateImageRequestBody,
        CreateMessageReactionRequest,
        CreateMessageReactionRequestBody,
        CreateMessageRequest,
        CreateMessageRequestBody,
        Emoji,
        GetMessageResourceRequest,
        P2ImMessageMessageReadV1,
        P2ImMessageReceiveV1,
    )

    FEISHU_AVAILABLE = True
except ImportError:
    FEISHU_AVAILABLE = False
    lark = None
    Emoji = None
    P2ImMessageMessageReadV1 = None
    P2ImMessageReceiveV1 = None

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

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        bus: MessageBus,
        encrypt_key: str = None,
        verification_token: str = None,
    ):
        # Config object simulation
        config = FeishuConfig(app_id, app_secret, encrypt_key, verification_token)

        super().__init__(config, bus)
        self.config = config
        self._client: Any = None
        self._ws_client: Any = None
        self._ws_process: multiprocessing.Process | None = None
        self._ws_queue: multiprocessing.Queue | None = None
        self._processed_message_ids: OrderedDict[str, None] = OrderedDict()  # Ordered dedup cache
        self._loop: asyncio.AbstractEventLoop | None = None
        # 新增：WebSocket重连机制
        self._ws_reconnect_delay = 5  # 初始重连延迟（秒）
        self._ws_max_reconnect_delay = 60  # 最大重连延迟（秒）
        self._ws_reconnect_attempts = 0
        self._ws_max_reconnect_attempts = 10  # 最大重连次数

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
            # 延迟获取事件循环，避免消息丢失
            def acquire_loop_later():
                import time
                for attempt in range(10):
                    time.sleep(1)
                    try:
                        self._loop = asyncio.get_running_loop()
                        logger.info("Successfully acquired event loop for Feishu channel")
                        return
                    except RuntimeError:
                        continue
                logger.error("Failed to acquire event loop after 10 attempts")
            threading.Thread(target=acquire_loop_later, daemon=True).start()

        # Create Lark client for sending messages
        self._client = (
            lark.Client.builder()
            .app_id(self.config.app_id)
            .app_secret(self.config.app_secret)
            .log_level(lark.LogLevel.INFO)
            .build()
        )

        # Create event handler (register message receive and message read events)
        event_handler = (
            lark.EventDispatcherHandler.builder(
                self.config.encrypt_key or "",
                self.config.verification_token or "",
            )
            .register_p2_im_message_receive_v1(self._on_message_sync)
            .register_p2_im_message_message_read_v1(self._on_message_read_sync)
            .build()
        )

        # Create WebSocket client for long connection
        self._ws_client = lark.ws.Client(
            self.config.app_id,
            self.config.app_secret,
            event_handler=event_handler,
            log_level=lark.LogLevel.INFO,
        )

        # Start WebSocket client in a separate PROCESS to avoid event loop conflict
        self._ws_queue = multiprocessing.Queue()
        self._ws_process = multiprocessing.Process(
            target=_feishu_ws_worker,
            args=(
                self.config.app_id,
                self.config.app_secret,
                self.config.encrypt_key or "",
                self.config.verification_token or "",
                self._ws_queue
            ),
            daemon=True
        )
        self._ws_process.start()
        logger.info(f"Feishu WebSocket worker process started (PID: {self._ws_process.pid})")
        
        # Start queue processor to handle messages from worker
        async def process_ws_queue():
            while self._running:
                try:
                    # Non-blocking queue get with timeout
                    msg_type, data = self._ws_queue.get_nowait()
                    if msg_type == "message":
                        # Schedule message handling in main event loop
                        if self._loop and self._loop.is_running():
                            asyncio.run_coroutine_threadsafe(self._on_message(data), self._loop)
                except Exception:
                    # Queue empty or other error
                    pass
                await asyncio.sleep(0.1)
        
        self._queue_processor_task = asyncio.create_task(process_ws_queue())
        
        logger.info("Feishu bot started with WebSocket subprocess")

        # Keep running until stopped
        while self._running:
            await asyncio.sleep(1)

    async def stop(self) -> None:
        """Stop the Feishu bot."""
        self._running = False
        
        # 关闭子进程
        if self._ws_process and self._ws_process.is_alive():
            logger.info("Stopping Feishu WebSocket worker process...")
            self._ws_process.terminate()
            self._ws_process.join(timeout=5.0)
            if self._ws_process.is_alive():
                logger.warning("Feishu WebSocket worker process did not terminate, killing...")
                self._ws_process.kill()
                self._ws_process.join(timeout=2.0)
        
        # 关闭队列处理任务
        if hasattr(self, '_queue_processor_task') and self._queue_processor_task:
            self._queue_processor_task.cancel()
            try:
                await self._queue_processor_task
            except asyncio.CancelledError:
                pass
        
        # 兼容旧代码：关闭线程（如果有）
        if hasattr(self, '_ws_thread') and self._ws_thread and self._ws_thread.is_alive():
            self._ws_thread.join(timeout=5.0)
            if self._ws_thread.is_alive():
                logger.warning("Feishu WebSocket thread did not terminate within timeout")
        
        logger.info("Feishu bot stopped")

    def _add_reaction_sync(self, message_id: str, emoji_type: str) -> None:
        """Sync helper for adding reaction (runs in thread pool)."""
        try:
            request = (
                CreateMessageReactionRequest.builder()
                .message_id(message_id)
                .request_body(
                    CreateMessageReactionRequestBody.builder()
                    .reaction_type(Emoji.builder().emoji_type(emoji_type).build())
                    .build()
                )
                .build()
            )

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
                request = (
                    CreateImageRequest.builder()
                    .request_body(
                        CreateImageRequestBody.builder().image_type("message").image(f).build()
                    )
                    .build()
                )
                response = self._client.im.v1.image.create(request)
                if not response.success():
                    raise Exception(f"Image upload failed: {response.code} {response.msg}")
                return response.data.image_key
            else:
                # Default to file
                request = (
                    CreateFileRequest.builder()
                    .request_body(
                        CreateFileRequestBody.builder()
                        .file_type("stream")
                        .file_name(file_name)
                        .duration(0)
                        .file(f)
                        .build()
                    )
                    .build()
                )
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

            # 1. Send text content if present (修复：空内容但有附件时跳过文本发送)
            if msg.content and msg.content.strip():
                content = json.dumps({"text": msg.content})
                request = (
                    CreateMessageRequest.builder()
                    .receive_id_type(receive_id_type)
                    .request_body(
                        CreateMessageRequestBody.builder()
                        .receive_id(msg.session_id)
                        .msg_type("text")
                        .content(content)
                        .build()
                    )
                    .build()
                )

                response = self._client.im.v1.message.create(request)
                if not response.success():
                    logger.error(
                        f"Failed to send Feishu text: code={response.code}, msg={response.msg}"
                    )
            elif not msg.media:
                # 如果既没有文本也没有附件，发送默认提示
                content = json.dumps({"text": "(empty message)"})
                request = (
                    CreateMessageRequest.builder()
                    .receive_id_type(receive_id_type)
                    .request_body(
                        CreateMessageRequestBody.builder()
                        .receive_id(msg.session_id)
                        .msg_type("text")
                        .content(content)
                        .build()
                    )
                    .build()
                )
                response = self._client.im.v1.message.create(request)
                if not response.success():
                    logger.error(
                        f"Failed to send Feishu text: code={response.code}, msg={response.msg}"
                    )

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

                            media_request = (
                                CreateMessageRequest.builder()
                                .receive_id_type(receive_id_type)
                                .request_body(
                                    CreateMessageRequestBody.builder()
                                    .receive_id(msg.session_id)
                                    .msg_type(file_type)
                                    .content(media_content)
                                    .build()
                                )
                                .build()
                            )

                            media_resp = self._client.im.v1.message.create(media_request)
                            if not media_resp.success():
                                logger.error(
                                    f"Failed to send Feishu media: code={media_resp.code}, msg={media_resp.msg}"
                                )

                        except Exception as upload_err:
                            logger.error(f"Failed to upload/send media {file_path}: {upload_err}")

        except Exception as e:
            logger.error(f"Error sending Feishu message: {e}")

    def _on_message_sync(self, data: "P2ImMessageReceiveV1") -> None:
        """
        Sync handler for incoming messages (called from WebSocket thread).
        Schedules async handling in the main event loop.
        """
        # 重试机制：如果事件循环尚未就绪，延迟重试
        if not self._loop or not self._loop.is_running():
            logger.warning("Main event loop not ready, scheduling retry for Feishu message")
            # 延迟重试机制
            def retry_later():
                import time
                for attempt in range(5):
                    time.sleep(0.5)
                    if self._loop and self._loop.is_running():
                        asyncio.run_coroutine_threadsafe(self._on_message(data), self._loop)
                        return
                logger.error("Failed to schedule Feishu message after 5 retries")
            threading.Thread(target=retry_later, daemon=True).start()
        else:
            asyncio.run_coroutine_threadsafe(self._on_message(data), self._loop)

    def _on_message_read_sync(self, data: Any) -> None:
        """
        Sync handler for message read events (called from WebSocket thread).
        This is a no-op handler to prevent "processor not found" errors.
        Message read receipts indicate when someone has read our messages.
        """
        # We don't need to do anything with read receipts currently,
        # but we must register this handler to avoid the "processor not found" error.
        logger.debug(f"Message read event received: {data}")

    def _download_feishu_file(
        self, message_id: str, file_key: str, file_type: str, file_name: str
    ) -> str:
        """Download a file from Feishu and return local path. Runs synchronously."""
        from pathlib import Path

        request = (
            GetMessageResourceRequest.builder()
            .message_id(message_id)
            .file_key(file_key)
            .type(file_type)
            .build()
        )

        response = self._client.im.v1.message_resource.get(request)
        if not response.success():
            raise Exception(f"Failed to get Feishu resource: {response.code} {response.msg}")

        # 修复：空指针检查 - response.file 可能为 None
        if response.file is None:
            raise Exception(f"Feishu response returned None file content for {file_key}")

        download_dir = Path("data/downloads")
        download_dir.mkdir(parents=True, exist_ok=True)

        file_path = download_dir / f"fs_{message_id}_{file_name}"

        with open(file_path, "wb") as f:
            # response.file may be a BytesIO object; get its bytes content
            file_data = (
                response.file.getvalue() if hasattr(response.file, "getvalue") else response.file
            )
            if not file_data:
                raise Exception(f"Feishu file content is empty for {file_key}")
            f.write(file_data)

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
            elif msg_type in ("image", "file", "audio", "video", "sticker"):
                try:
                    parsed_content = json.loads(message.content)
                    file_key = parsed_content.get("file_key") or parsed_content.get("image_key")

                    if file_key:
                        file_name = parsed_content.get("file_name", f"{file_key}.{msg_type}")
                        resource_type = "image" if msg_type == "image" else msg_type

                        loop = asyncio.get_running_loop()
                        file_path = await loop.run_in_executor(
                            None,
                            self._download_feishu_file,
                            message_id,
                            file_key,
                            resource_type,
                            file_name,
                        )

                        content = f"[System] User sent a {resource_type}: {file_name}"
                        media_items.append(
                            {
                                "type": resource_type,
                                "path": file_path,
                                "name": file_name,
                            }
                        )
                        logger.info(f"Downloaded Feishu {resource_type}: {file_path}")
                    else:
                        content = MSG_TYPE_MAP.get(msg_type, f"[{msg_type}]")
                except Exception as e:
                    logger.error(f"Failed to process Feishu media {msg_type}: {e}")
                    content = (
                        f"[System] User attempted to send a {msg_type}, but processing failed."
                    )
            elif msg_type == "rich_text":
                # 处理富文本消息
                try:
                    parsed_content = json.loads(message.content)
                    # 提取纯文本内容
                    text_parts = []
                    for block in parsed_content.get("content", []):
                        if isinstance(block, dict):
                            for run in block.get("runs", []):
                                if "text" in run:
                                    text_parts.append(run["text"])
                    content = "".join(text_parts) if text_parts else "[Rich text message]"
                except Exception as e:
                    logger.error(f"Failed to process Feishu rich text: {e}")
                    content = "[Rich text message - parsing failed]"
            else:
                # 处理其他未知消息类型
                content = MSG_TYPE_MAP.get(msg_type, f"[{msg_type}]")
                logger.warning(f"Received unsupported message type: {msg_type}")

            if not content and not media_items:
                return

            # Forward to message bus
            reply_to = session_id

            logger.info(f"Received Feishu message from {sender_id}: {content[:30]}...")

            await self._handle_message(
                sender_id=sender_id,
                session_id=session_id,
                content=content,
                media=media_items,  # Pass media up to the base class handler
                metadata={
                    "message_id": message_id,
                    "chat_type": chat_type,
                    "msg_type": msg_type,
                    "username": sender.sender_id.user_id,  # No username in public event usually, just IDs
                },
            )

        except Exception as e:
            logger.error(f"Error processing Feishu message: {e}")
