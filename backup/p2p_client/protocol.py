# -*- coding: utf-8 -*-
"""
消息协议模块

定义 P2P 网络中使用的消息类型和协议处理
"""

import json
import asyncio
from typing import Dict, Callable, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum
import time


# 协议标识符
COMMUNITY_PROTOCOL = "/bit-politeia/1.0.0"


class MessageType(Enum):
    """消息类型枚举"""
    DIRECT = "DIRECT"           # 点对点直接消息
    GROUP = "GROUP"             # 小组广播消息
    SYNC_REQUEST = "SYNC_REQ"   # 请求同步网络结构
    SYNC_RESPONSE = "SYNC_RES"  # 同步响应
    JOIN_GROUP = "JOIN_GROUP"   # 加入小组请求
    LEAVE_GROUP = "LEAVE_GROUP" # 离开小组通知
    PING = "PING"               # 心跳检测
    PONG = "PONG"               # 心跳响应


@dataclass
class Message:
    """消息数据结构"""
    msg_type: str           # 消息类型
    from_peer: str          # 发送者 Peer ID
    to_target: str          # 目标（节点 ID 或小组 ID）
    content: Any            # 消息内容
    timestamp: float        # 时间戳
    msg_id: Optional[str] = None  # 消息 ID（可选）
    
    def to_json(self) -> str:
        """序列化为 JSON 字符串"""
        return json.dumps(asdict(self))
    
    @classmethod
    def from_json(cls, json_str: str) -> 'Message':
        """从 JSON 字符串反序列化"""
        data = json.loads(json_str)
        return cls(**data)
    
    def to_bytes(self) -> bytes:
        """转换为字节串用于网络传输"""
        return self.to_json().encode('utf-8')
    
    @classmethod
    def from_bytes(cls, data: bytes) -> 'Message':
        """从字节串解析"""
        return cls.from_json(data.decode('utf-8'))


class MessageHandler:
    """
    消息处理器
    
    负责处理接收到的消息和发送消息
    """
    
    def __init__(self, p2p_host):
        """
        初始化消息处理器
        
        Args:
            p2p_host: P2PHost 实例
        """
        self._host = p2p_host
        self._handlers: Dict[str, Callable] = {}
        self._message_queue: asyncio.Queue = asyncio.Queue()
        self._running = False
        
        # 注册协议处理器
        self._host.set_stream_handler(COMMUNITY_PROTOCOL, self._handle_stream)
    
    def register_handler(self, msg_type: str, handler: Callable[[Message], Any]):
        """
        注册消息类型处理器
        
        Args:
            msg_type: 消息类型
            handler: 处理函数，接收 Message 对象
        """
        self._handlers[msg_type] = handler
    
    async def _handle_stream(self, stream):
        """
        处理接收到的流
        
        Args:
            stream: libp2p 网络流
        """
        try:
            # 读取消息数据
            data = await stream.read()
            if not data:
                return
            
            # 解析消息
            message = Message.from_bytes(data)
            
            # 查找并调用处理器
            handler = self._handlers.get(message.msg_type)
            if handler:
                await self._call_handler(handler, message)
            else:
                print(f"[协议] 未知消息类型: {message.msg_type}")
                
        except Exception as e:
            print(f"[协议] 处理流错误: {e}")
        finally:
            await stream.close()
    
    async def _call_handler(self, handler: Callable, message: Message):
        """安全调用处理器"""
        try:
            result = handler(message)
            if asyncio.iscoroutine(result):
                await result
        except Exception as e:
            print(f"[协议] 处理器错误: {e}")
    
    async def send_message(self, peer_id: str, message: Message) -> bool:
        """
        发送消息到指定节点
        
        Args:
            peer_id: 目标节点 Peer ID
            message: 消息对象
            
        Returns:
            bool: 发送是否成功
        """
        try:
            if self._host.simulate_mode:
                # 模拟模式：直接调用本地处理器
                print(f"[协议-模拟] 发送 {message.msg_type} 到 {peer_id}")
                handler = self._handlers.get(message.msg_type)
                if handler:
                    await self._call_handler(handler, message)
                return True
            
            # 创建到目标节点的流
            stream = await self._host.new_stream(peer_id, COMMUNITY_PROTOCOL)
            if not stream:
                return False
            
            # 发送消息
            await stream.write(message.to_bytes())
            await stream.close()
            
            return True
            
        except Exception as e:
            print(f"[协议] 发送消息失败: {e}")
            return False
    
    def create_message(
        self,
        msg_type: str,
        to_target: str,
        content: Any,
        msg_id: Optional[str] = None
    ) -> Message:
        """
        创建消息对象
        
        Args:
            msg_type: 消息类型
            to_target: 目标
            content: 消息内容
            msg_id: 可选的消息 ID
            
        Returns:
            Message: 消息对象
        """
        import secrets
        return Message(
            msg_type=msg_type,
            from_peer=self._host.get_peer_id(),
            to_target=to_target,
            content=content,
            timestamp=time.time(),
            msg_id=msg_id or secrets.token_hex(8)
        )
    
    async def send_direct_message(self, peer_id: str, content: str) -> bool:
        """
        发送直接消息
        
        Args:
            peer_id: 目标节点 ID
            content: 消息内容
            
        Returns:
            bool: 发送是否成功
        """
        message = self.create_message(
            msg_type=MessageType.DIRECT.value,
            to_target=peer_id,
            content=content
        )
        return await self.send_message(peer_id, message)
    
    async def send_ping(self, peer_id: str) -> bool:
        """发送心跳检测"""
        message = self.create_message(
            msg_type=MessageType.PING.value,
            to_target=peer_id,
            content={"ping_time": time.time()}
        )
        return await self.send_message(peer_id, message)
