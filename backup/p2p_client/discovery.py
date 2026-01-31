# -*- coding: utf-8 -*-
"""
节点发现模块

提供 mDNS 局域网发现和引导节点连接功能
"""

import asyncio
from typing import List, Dict, Set, Optional, Callable
from dataclasses import dataclass
import socket
import json


@dataclass
class DiscoveredPeer:
    """发现的节点信息"""
    peer_id: str
    multiaddrs: List[str]
    discovered_at: float  # 发现时间戳


class PeerDiscovery:
    """
    节点发现服务
    
    支持以下发现机制:
    - mDNS 局域网自动发现
    - 引导节点连接
    - 手动添加节点
    """
    
    # mDNS 服务配置
    MDNS_SERVICE_TYPE = "_bit-politeia._tcp.local."
    MDNS_PORT = 5353
    
    def __init__(self, p2p_host):
        """
        初始化发现服务
        
        Args:
            p2p_host: P2PHost 实例
        """
        self._host = p2p_host
        self._known_peers: Dict[str, DiscoveredPeer] = {}
        self._bootstrap_nodes: List[str] = []
        self._discovery_handlers: List[Callable] = []
        self._mdns_running = False
        self._discovery_task = None
    
    def add_peer_discovered_handler(self, handler: Callable[[DiscoveredPeer], None]):
        """
        添加节点发现回调处理器
        
        Args:
            handler: 发现新节点时调用的函数
        """
        self._discovery_handlers.append(handler)
    
    def _notify_peer_discovered(self, peer: DiscoveredPeer):
        """通知所有处理器新节点被发现"""
        for handler in self._discovery_handlers:
            try:
                handler(peer)
            except Exception as e:
                print(f"[发现] 处理器错误: {e}")
    
    async def start_mdns_discovery(self):
        """
        启动 mDNS 局域网发现服务
        
        使用 UDP 多播在局域网中广播和发现其他节点
        """
        if self._mdns_running:
            return
        
        self._mdns_running = True
        print("[发现] 启动 mDNS 发现服务...")
        
        # 启动发现循环
        self._discovery_task = asyncio.create_task(self._mdns_discovery_loop())
    
    async def _mdns_discovery_loop(self):
        """mDNS 发现主循环"""
        # 创建 UDP socket 用于多播
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setblocking(False)
        
        # 多播地址
        MCAST_GRP = '224.0.0.251'
        MCAST_PORT = 5353
        
        try:
            sock.bind(('', MCAST_PORT))
            # 加入多播组
            import struct
            mreq = struct.pack("4sl", socket.inet_aton(MCAST_GRP), socket.INADDR_ANY)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        except Exception as e:
            print(f"[发现] mDNS 绑定失败: {e}，使用简化发现模式")
            sock.close()
            return
        
        loop = asyncio.get_event_loop()
        
        while self._mdns_running:
            try:
                # 广播自己的信息
                await self._broadcast_presence(sock, MCAST_GRP, MCAST_PORT)
                
                # 接收其他节点的广播
                try:
                    data, addr = await asyncio.wait_for(
                        loop.run_in_executor(None, lambda: sock.recvfrom(1024)),
                        timeout=1.0
                    )
                    await self._handle_discovery_message(data, addr)
                except asyncio.TimeoutError:
                    pass
                
                await asyncio.sleep(5)  # 每5秒广播一次
                
            except Exception as e:
                print(f"[发现] mDNS 错误: {e}")
                await asyncio.sleep(1)
        
        sock.close()
    
    async def _broadcast_presence(self, sock, mcast_grp: str, mcast_port: int):
        """广播自己的存在信息"""
        presence = {
            'type': 'bit-politeia-presence',
            'peer_id': self._host.get_peer_id(),
            'multiaddrs': self._host.get_multiaddrs()
        }
        try:
            sock.sendto(json.dumps(presence).encode(), (mcast_grp, mcast_port))
        except Exception as e:
            pass  # 忽略发送错误
    
    async def _handle_discovery_message(self, data: bytes, addr: tuple):
        """处理发现消息"""
        try:
            message = json.loads(data.decode())
            if message.get('type') != 'bit-politeia-presence':
                return
            
            peer_id = message.get('peer_id')
            if not peer_id or peer_id == self._host.get_peer_id():
                return  # 忽略自己
            
            multiaddrs = message.get('multiaddrs', [])
            
            # 检查是否是新节点
            if peer_id not in self._known_peers:
                import time
                peer = DiscoveredPeer(
                    peer_id=peer_id,
                    multiaddrs=multiaddrs,
                    discovered_at=time.time()
                )
                self._known_peers[peer_id] = peer
                print(f"[发现] 发现新节点: {peer_id}")
                self._notify_peer_discovered(peer)
                
        except json.JSONDecodeError:
            pass  # 忽略无效消息
    
    async def stop_mdns_discovery(self):
        """停止 mDNS 发现服务"""
        self._mdns_running = False
        if self._discovery_task:
            self._discovery_task.cancel()
            try:
                await self._discovery_task
            except asyncio.CancelledError:
                pass
        print("[发现] mDNS 发现服务已停止")
    
    async def connect_bootstrap_nodes(self, nodes: List[str]) -> int:
        """
        连接到引导节点
        
        Args:
            nodes: 引导节点的多地址列表
            
        Returns:
            int: 成功连接的节点数量
        """
        self._bootstrap_nodes = nodes
        connected = 0
        
        for node_addr in nodes:
            try:
                success = await self._host.connect_to_peer(node_addr)
                if success:
                    connected += 1
                    # 提取 peer_id
                    peer_id = node_addr.split("/p2p/")[-1] if "/p2p/" in node_addr else None
                    if peer_id:
                        import time
                        peer = DiscoveredPeer(
                            peer_id=peer_id,
                            multiaddrs=[node_addr],
                            discovered_at=time.time()
                        )
                        self._known_peers[peer_id] = peer
            except Exception as e:
                print(f"[发现] 连接引导节点失败 {node_addr}: {e}")
        
        print(f"[发现] 已连接 {connected}/{len(nodes)} 个引导节点")
        return connected
    
    def add_known_peer(self, peer_id: str, multiaddrs: List[str]):
        """
        手动添加已知节点
        
        Args:
            peer_id: 节点 ID
            multiaddrs: 节点地址列表
        """
        import time
        peer = DiscoveredPeer(
            peer_id=peer_id,
            multiaddrs=multiaddrs,
            discovered_at=time.time()
        )
        self._known_peers[peer_id] = peer
    
    def get_known_peers(self) -> List[DiscoveredPeer]:
        """获取所有已知节点列表"""
        return list(self._known_peers.values())
    
    def get_peer_by_id(self, peer_id: str) -> Optional[DiscoveredPeer]:
        """根据 ID 获取节点信息"""
        return self._known_peers.get(peer_id)
    
    def remove_peer(self, peer_id: str):
        """移除已知节点"""
        if peer_id in self._known_peers:
            del self._known_peers[peer_id]
