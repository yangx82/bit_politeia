import sqlite3
import logging
import json
from typing import List, Dict, Optional, Set, Any
from datetime import datetime
import os

from ..p2p_community.bootstrap_client import GroupInfo, PeerAddress, NodeRegistration

logger = logging.getLogger(__name__)

class BootstrapStorage:
    def __init__(self, db_path: str = "bootstrap.db"):
        # Ensure db_path is absolute or relative to backend root?
        # Let's make it relative to cwd if not absolute
        self.db_path = db_path
        self._init_db()

    def _get_conn(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        """Initialize database schema."""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        # Groups Table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS groups (
                group_id TEXT PRIMARY KEY,
                level INTEGER,
                parent_id TEXT,
                name TEXT,
                member_count INTEGER,
                max_capacity INTEGER,
                has_space BOOLEAN,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Nodes Table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS nodes (
                node_id TEXT PRIMARY KEY,
                public_key TEXT,
                ip_address TEXT,
                port INTEGER,
                name TEXT,
                last_seen TIMESTAMP
            )
        ''')

        # Group Members (Many-to-Many)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS group_members (
                group_id TEXT,
                node_id TEXT,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (group_id, node_id),
                FOREIGN KEY(group_id) REFERENCES groups(group_id),
                FOREIGN KEY(node_id) REFERENCES nodes(node_id)
            )
        ''')

        # Group Core Nodes (Order matters? Usually lists are small, but we store as simple relation)
        # We can store order or just set
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS group_core_nodes (
                group_id TEXT,
                node_id TEXT,
                is_proxy BOOLEAN DEFAULT 0,
                PRIMARY KEY (group_id, node_id),
                FOREIGN KEY(group_id) REFERENCES groups(group_id),
                FOREIGN KEY(node_id) REFERENCES nodes(node_id)
            )
        ''')

        # Pending Joins
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS pending_joins (
                group_id TEXT,
                node_id TEXT,
                public_key TEXT,
                ip_address TEXT,
                port INTEGER,
                name TEXT,
                requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (group_id, node_id)
            )
        ''')

        # Group Rankings (Order matters greatly)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS group_rankings (
                group_id TEXT,
                node_id TEXT,
                rank_order INTEGER,
                PRIMARY KEY (group_id, node_id)
            )
        ''')

        # Tunnel Allocations (for frp)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tunnel_allocations (
                node_id TEXT PRIMARY KEY,
                remote_port INTEGER UNIQUE,
                allocated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        conn.commit()
        conn.close()

    # --- Groups ---

    def upsert_group(self, group: GroupInfo):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO groups (group_id, level, parent_id, name, member_count, max_capacity, has_space)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(group_id) DO UPDATE SET
                level=excluded.level,
                parent_id=excluded.parent_id,
                name=excluded.name,
                member_count=excluded.member_count,
                max_capacity=excluded.max_capacity,
                has_space=excluded.has_space
        ''', (
            group.group_id, group.level, group.parent_id, group.name,
            group.member_count, group.max_capacity, group.has_space
        ))
        conn.commit()
        
        # Update Core Nodes
        self._update_group_relations(conn, group)
        conn.close()

    def _update_group_relations(self, conn, group: GroupInfo):
        cursor = conn.cursor()
        
        # Sync Core Nodes
        cursor.execute('DELETE FROM group_core_nodes WHERE group_id = ?', (group.group_id,))
        if group.core_node_ids:
            cursor.executemany(
                'INSERT INTO group_core_nodes (group_id, node_id) VALUES (?, ?)',
                [(group.group_id, nid) for nid in group.core_node_ids]
            )

        # Sync Rankings
        cursor.execute('DELETE FROM group_rankings WHERE group_id = ?', (group.group_id,))
        if group.node_rankings:
            cursor.executemany(
                'INSERT INTO group_rankings (group_id, node_id, rank_order) VALUES (?, ?, ?)',
                [(group.group_id, nid, idx) for idx, nid in enumerate(group.node_rankings)]
            )
        conn.commit()

    def load_groups(self) -> Dict[str, GroupInfo]:
        conn = self._get_conn()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        groups = {}
        cursor.execute('SELECT * FROM groups')
        rows = cursor.fetchall()
        
        for row in rows:
            gid = row['group_id']
            
            # Load Relations
            cursor.execute('SELECT node_id FROM group_core_nodes WHERE group_id = ?', (gid,))
            cores = [r[0] for r in cursor.fetchall()]

            cursor.execute('SELECT node_id FROM group_rankings WHERE group_id = ? ORDER BY rank_order ASC', (gid,))
            rankings = [r[0] for r in cursor.fetchall()]

            groups[gid] = GroupInfo(
                group_id=gid,
                level=row['level'],
                parent_id=row['parent_id'],
                name=row['name'],
                member_count=row['member_count'],
                max_capacity=row['max_capacity'],
                has_space=bool(row['has_space']),
                core_node_ids=cores,
                node_rankings=rankings
            )
        
        conn.close()
        return groups

    def load_group_members(self) -> Dict[str, Set[str]]:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('SELECT group_id, node_id FROM group_members')
        rows = cursor.fetchall()
        conn.close()
        
        mapping = {}
        for gid, nid in rows:
            if gid not in mapping: mapping[gid] = set()
            mapping[gid].add(nid)
        return mapping

    # --- Nodes ---

    def upsert_node(self, node: PeerAddress):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO nodes (node_id, public_key, ip_address, port, name, last_seen)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(node_id) DO UPDATE SET
                public_key=excluded.public_key,
                ip_address=excluded.ip_address,
                port=excluded.port,
                name=excluded.name,
                last_seen=excluded.last_seen
        ''', (
            node.node_id, node.public_key, node.ip_address, node.port, 
            node.name, node.last_seen.isoformat() if node.last_seen else None
        ))
        conn.commit()
        conn.close()

    def load_nodes(self) -> Dict[str, PeerAddress]:
        conn = self._get_conn()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM nodes')
        rows = cursor.fetchall()
        conn.close()
        
        from datetime import timezone
        nodes = {}
        for row in rows:
            nodes[row['node_id']] = PeerAddress(
                node_id=row['node_id'],
                public_key=row['public_key'],
                ip_address=row['ip_address'],
                port=row['port'],
                name=row['name'],
                last_seen=datetime.fromisoformat(row['last_seen']) if row['last_seen'] else datetime.now(timezone.utc)
            )
        return nodes

    # --- Memberships ---

    def add_group_member(self, group_id: str, node_id: str):
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute('INSERT INTO group_members (group_id, node_id) VALUES (?, ?)', (group_id, node_id))
            conn.commit()
        except sqlite3.IntegrityError:
            pass # Already exists
        conn.close()
    
    def remove_group_member(self, group_id: str, node_id: str):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM group_members WHERE group_id=? AND node_id=?', (group_id, node_id))
        conn.commit()
        conn.close()

    def delete_node(self, node_id: str):
        """Perform a full deletion of a node from the registry and all group relations."""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        # 1. Remove from group memberships
        cursor.execute('DELETE FROM group_members WHERE node_id=?', (node_id,))
        
        # 2. Remove from core node designations
        cursor.execute('DELETE FROM group_core_nodes WHERE node_id=?', (node_id,))
        
        # 3. Remove from rankings
        cursor.execute('DELETE FROM group_rankings WHERE node_id=?', (node_id,))
        
        # 4. Remove from pending joins
        cursor.execute('DELETE FROM pending_joins WHERE node_id=?', (node_id,))
        
        # 5. Finally, remove from nodes table
        cursor.execute('DELETE FROM nodes WHERE node_id=?', (node_id,))
        
        conn.commit()
        conn.close()
        logger.info(f"Storage: Node {node_id} and all its relations deleted.")

    # --- Pending Joins ---

    def add_pending_join(self, group_id: str, reg: NodeRegistration):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO pending_joins (group_id, node_id, public_key, ip_address, port, name)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            group_id, reg.node_id, reg.public_key, reg.ip_address, reg.port, reg.name
        ))
        conn.commit()
        conn.close()

    def remove_pending_join(self, group_id: str, node_id: str):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM pending_joins WHERE group_id=? AND node_id=?', (group_id, node_id))
        conn.commit()
        conn.close()

    def load_pending_joins(self) -> Dict[str, List[NodeRegistration]]:
        conn = self._get_conn()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM pending_joins')
        rows = cursor.fetchall()
        conn.close()
        
        pending = {}
        for row in rows:
            gid = row['group_id']
            if gid not in pending: pending[gid] = []
            
            pending[gid].append(NodeRegistration(
                node_id=row['node_id'],
                public_key=row['public_key'],
                ip_address=row['ip_address'],
                port=row['port'],
                name=row['name'],
                group_id=gid
            ))
        return pending

    # --- Tunnel Allocations ---

    def upsert_tunnel_allocation(self, node_id: str, remote_port: int):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO tunnel_allocations (node_id, remote_port)
            VALUES (?, ?)
            ON CONFLICT(node_id) DO UPDATE SET
                remote_port=excluded.remote_port
        ''', (node_id, remote_port))
        conn.commit()
        conn.close()

    def load_tunnel_allocations(self) -> Dict[str, int]:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('SELECT node_id, remote_port FROM tunnel_allocations')
        rows = cursor.fetchall()
        conn.close()
        return {row[0]: row[1] for row in rows}

    def delete_tunnel_allocation(self, node_id: str):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM tunnel_allocations WHERE node_id=?', (node_id,))
        conn.commit()
        conn.close()
