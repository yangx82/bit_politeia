# -*- coding: utf-8 -*-
"""
P2P 主机封装模块

封装 libp2p 主机的创建和管理
"""

import asyncio
import secrets
from typing import Optional, Callable, Any
from dataclasses import dataclass

try:
    from libp2p import new_host
    from libp2p.crypto.secp256k1 import create_new_key_pair
    from libp2p.network.stream.net_stream_interface import INetStream
    from libp2p.peer.peerinfo import info_from_p2p_addr
    from libp2p.typing import TProtocol
    from multiaddr import Multiaddr
    LIBP2P_AVAILABLE = True
except ImportError:
    LIBP2P_AVAILABLE = False
    print("警告: libp2p 未安装，将使用模拟模式")


@dataclass
class PeerInfo:
    """节点信息"""
    peer_id: str
    multiaddrs: list


class P2PHost:
    """
    P2P 主机封装类
    
    负责创建和管理 libp2p 主机实例，处理连接和协议注册
    """
    
    def __init__(self):
        self._host = None
        self._key_pair = None
        self._running = False
        self._protocol_handlers: dict = {}
        
        # 模拟模式支持（当 libp2p 不可用时）
        self._simulate_mode = not LIBP2P_AVAILABLE
        self._simulated_peer_id = None
        self._simulated_connections: dict = {}
    
    async def create_host(self, private_key: Optional[bytes] = None, listen_port: int = 0) -> 'P2PHost':
        """
        创建并初始化 libp2p 主机
        
        Args:
            private_key: 可选的私钥，用于生成固定的 Peer ID
            listen_port: 监听端口，0 表示随机端口
            
        Returns:
            self: 当前主机实例
        """
        if self._simulate_mode:
            # 模拟模式：生成假的 Peer ID
            self._simulated_peer_id = f"QmSimulated{secrets.token_hex(8)}"
            self._running = True
            print(f"[模拟模式] 节点已启动，Peer ID: {self._simulated_peer_id}")
            return self
        
        # 创建密钥对
        if private_key:
            # 从提供的私钥创建密钥对
            self._key_pair = create_new_key_pair(private_key)
        else:
            # 生成新的密钥对
            self._key_pair = create_new_key_pair()
        
        # 创建主机
        self._host = new_host(key_pair=self._key_pair)
        
        # 设置监听地址
        listen_addr = Multiaddr(f"/ip4/0.0.0.0/tcp/{listen_port}")
        
        # 启动主机
        async with self._host.run(listen_addrs=[listen_addr]):
            self._running = True
            print(f"[P2P] 节点已启动")
            print(f"[P2P] Peer ID: {self.get_peer_id()}")
            for addr in self._host.get_addrs():
                print(f"[P2P] 监听地址: {addr}")
        
        return self
    
    async def start(self, listen_port: int = 0):
        """
        启动主机并保持运行
        
        Args:
            listen_port: 监听端口
        """
        if self._simulate_mode:
            self._simulated_peer_id = f"QmSimulated{secrets.token_hex(8)}"
            self._running = True
            return
        
        if not self._key_pair:
            self._key_pair = create_new_key_pair()
        
        self._host = new_host(key_pair=self._key_pair)
        listen_addr = Multiaddr(f"/ip4/0.0.0.0/tcp/{listen_port}")
        
        # 注册所有协议处理器
        for protocol_id, handler in self._protocol_handlers.items():
            self._host.set_stream_handler(TProtocol(protocol_id), handler)
        
        await self._host.get_network().listen(listen_addr)
        self._running = True
        
        print(f"[P2P] 节点已启动，Peer ID: {self.get_peer_id()}")
        for addr in self._host.get_addrs():
            print(f"[P2P] 监听地址: {addr}")
    
    async def stop(self):
        """停止主机"""
        self._running = False
        if self._host:
            await self._host.close()
        print("[P2P] 节点已停止")
    
    def get_peer_id(self) -> str:
        """获取当前节点的 Peer ID"""
        if self._simulate_mode:
            return self._simulated_peer_id or "未初始化"
        if self._host:
            return str(self._host.get_id())
        return "未初始化"
    
    def get_multiaddrs(self) -> list:
        """获取当前节点的多地址列表"""
        if self._simulate_mode:
            return [f"/ip4/127.0.0.1/tcp/8000/p2p/{self._simulated_peer_id}"]
        if self._host:
            return [f"{addr}/p2p/{self.get_peer_id()}" for addr in self._host.get_addrs()]
        return []
    
    async def connect_to_peer(self, multiaddr_str: str) -> bool:
        """
        连接到指定的对等节点
        
        Args:
            multiaddr_str: 目标节点的多地址字符串
            
        Returns:
            bool: 连接是否成功
        """
        if self._simulate_mode:
            # 模拟模式：记录连接
            peer_id = multiaddr_str.split("/p2p/")[-1] if "/p2p/" in multiaddr_str else multiaddr_str
            self._simulated_connections[peer_id] = multiaddr_str
            print(f"[模拟模式] 已连接到节点: {peer_id}")
            return True
        
        try:
            maddr = Multiaddr(multiaddr_str)
            peer_info = info_from_p2p_addr(maddr)
            await self._host.connect(peer_info)
            print(f"[P2P] 已连接到节点: {peer_info.peer_id}")
            return True
        except Exception as e:
            print(f"[P2P] 连接失败: {e}")
            return False
    
    def set_stream_handler(self, protocol_id: str, handler: Callable):
        """
        注册协议流处理器
        
        Args:
            protocol_id: 协议标识符
            handler: 处理函数
        """
        self._protocol_handlers[protocol_id] = handler
        if self._host and not self._simulate_mode:
            self._host.set_stream_handler(TProtocol(protocol_id), handler)
    
    async def new_stream(self, peer_id: str, protocol_id: str):
        """
        创建到指定节点的新流
        
        Args:
            peer_id: 目标节点 ID
            protocol_id: 协议标识符
            
        Returns:
            stream: 网络流对象
        """
        if self._simulate_mode:
            print(f"[模拟模式] 创建流到 {peer_id}，协议: {protocol_id}")
            return None
        
        from libp2p.peer.id import ID
        target_peer_id = ID.from_base58(peer_id)
        stream = await self._host.new_stream(target_peer_id, [TProtocol(protocol_id)])
        return stream
    
    def get_connected_peers(self) -> list:
        """获取已连接的节点列表"""
        if self._simulate_mode:
            return list(self._simulated_connections.keys())
        if self._host:
            return [str(peer_id) for peer_id in self._host.get_network().get_connections()]
        return []
    
    @property
    def is_running(self) -> bool:
        """检查主机是否正在运行"""
        return self._running
    
    @property
    def simulate_mode(self) -> bool:
        """检查是否在模拟模式下运行"""
        return self._simulate_mode
