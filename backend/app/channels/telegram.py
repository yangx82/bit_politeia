"""Telegram channel implementation using python-telegram-bot."""

import asyncio
import re
import logging
import os
from pathlib import Path
from typing import Any

from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes, CommandHandler

from ..bus.events import OutboundMessage
from ..bus.queue import MessageBus
from .base import BaseChannel

logger = logging.getLogger(__name__)

def _markdown_to_telegram_html(text: str) -> str:
    """
    Convert markdown to Telegram-safe HTML.
    Adapted from Nanobot.
    """
    if not text:
        return ""
    
    # 1. Extract and protect code blocks
    code_blocks = []
    def save_code_block(m: re.Match) -> str:
        code_blocks.append(m.group(1))
        return f"\x00CB{len(code_blocks) - 1}\x00"
    
    text = re.sub(r'```[\w]*\n?([\s\S]*?)```', save_code_block, text)
    
    # 2. Extract and protect inline code
    inline_codes = []
    def save_inline_code(m: re.Match) -> str:
        inline_codes.append(m.group(1))
        return f"\x00IC{len(inline_codes) - 1}\x00"
    
    text = re.sub(r'`([^`]+)`', save_inline_code, text)
    
    # 3. Headers
    text = re.sub(r'^#{1,6}\s+(.+)$', r'<b>\1</b>', text, flags=re.MULTILINE)
    
    # 4. Blockquotes
    text = re.sub(r'^>\s*(.*)$', r'<i>\1</i>', text, flags=re.MULTILINE)
    
    # 5. Escape HTML special characters
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    
    # 6. Links
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', text)
    
    # 7. Bold
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'__(.+?)__', r'<b>\1</b>', text)
    
    # 8. Italic
    text = re.sub(r'(?<![a-zA-Z0-9])_([^_]+)_(?![a-zA-Z0-9])', r'<i>\1</i>', text)
    
    # 9. Strikethrough
    text = re.sub(r'~~(.+?)~~', r'<s>\1</s>', text)
    
    # 10. Bullet lists
    text = re.sub(r'^[-*]\s+', '• ', text, flags=re.MULTILINE)
    
    # 11. Restore inline code
    for i, code in enumerate(inline_codes):
        escaped = code.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        text = text.replace(f"\x00IC{i}\x00", f"<code>{escaped}</code>")
    
    # 12. Restore code blocks
    for i, code in enumerate(code_blocks):
        escaped = code.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        text = text.replace(f"\x00CB{i}\x00", f"<pre><code>{escaped}</code></pre>")
    
    return text


class TelegramChannel(BaseChannel):
    """
    Telegram channel using long polling.
    """
    
    name = "telegram"
    
    def __init__(self, token: str, bus: MessageBus, allow_from: list = None):
        # We pass a simple config dict-like object
        config = type('Config', (), {'allow_from': allow_from or []})()
        super().__init__(config, bus)
        self.token = token
        self._app: Application | None = None
        self._chat_ids: dict[str, int] = {}  # Map sender_id to chat_id for replies
    
    async def start(self) -> None:
        """Start the Telegram bot."""
        if not self.token:
            logger.error("Telegram bot token not configured")
            return
        
        self._running = True
        
        self._app = Application.builder().token(self.token).build()
        
        # Handlers
        self._app.add_handler(
            MessageHandler(
                (filters.TEXT | filters.PHOTO | filters.Document.ALL) & ~filters.COMMAND, 
                self._on_message
            )
        )
        self._app.add_handler(CommandHandler("start", self._on_start))
        
        logger.info("Starting Telegram bot (polling)...")
        
        await self._app.initialize()
        await self._app.start()
        
        bot_info = await self._app.bot.get_me()
        logger.info(f"Telegram bot @{bot_info.username} connected")
        
        await self._app.updater.start_polling(allowed_updates=["message"], drop_pending_updates=True)
        
        # Keep running
        while self._running:
            await asyncio.sleep(1)
    
    async def stop(self) -> None:
        """Stop the Telegram bot."""
        self._running = False
        if self._app:
            logger.info("Stopping Telegram bot...")
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
            self._app = None
    
    async def send(self, msg: OutboundMessage) -> None:
        """Send a message through Telegram."""
        if not self._app:
            logger.warning("Telegram bot not running, cannot send message")
            return
        
        try:
            chat_id = int(msg.chat_id)
            html_content = _markdown_to_telegram_html(msg.content)
            await self._app.bot.send_message(chat_id=chat_id, text=html_content, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Error sending Telegram message: {e}")
            try:
                 # Fallback
                 await self._app.bot.send_message(chat_id=int(msg.chat_id), text=msg.content)
            except Exception as e2:
                 logger.error(f"Fallback send failed: {e2}")

    async def _on_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.effective_user:
            return
        await update.message.reply_text("👋 Hello! I am your Bit Politeia Resident Agent.")

    async def _on_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.effective_user:
            return
        
        message = update.message
        user = update.effective_user
        chat_id = message.chat_id
        
        # ID format: "userid"
        sender_id = str(user.id)
        
        # Handle Text
        content = message.text or message.caption or "[media]"
        
        # Handle Media (simple placeholder for now)
        if message.photo:
            content += " [Image received]"
        
        # Forward to Bus
        logger.info(f"Received Telegram message from {sender_id}: {content}")
        await self._handle_message(
            sender_id=sender_id,
            chat_id=str(chat_id),
            content=content,
            metadata={
                "username": user.username,
                "first_name": user.first_name,
                "platform": "telegram"
            }
        )
