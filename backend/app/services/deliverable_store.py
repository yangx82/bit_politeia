"""
Deliverable Store - 成果物统一存储系统

P2 改进：为任务交付物提供统一的存储、归档和审计接口。
"""

import os
import json
import shutil
import hashlib
from datetime import datetime
from typing import Dict, Any, List, Optional
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class DeliverableStore:
    """
    成果物统一存储管理器
    
    目录结构:
    data/deliverables/
    ├── messages/          # 已发送消息的记录
    ├── files/             # 创建的文件副本
    ├── votes/             # 投票记录
    ├── payments/          # 转账记录
    ├── analyses/          # 分析报告
    ├── research/          # 研究成果
    ├── code/              # 代码变更
    └── configs/           # 配置变更
    """
    
    # 交付物类型到目录的映射
    TYPE_DIRS = {
        "message": "messages",
        "file": "files",
        "vote": "votes",
        "payment": "payments",
        "analysis": "analyses",
        "research": "research",
        "code": "code",
        "config": "configs"
    }
    
    def __init__(self, base_dir: str = "data/deliverables"):
        self.base_dir = Path(base_dir)
        self._ensure_directories()
        self.index_file = self.base_dir / "index.json"
        self.index = self._load_index()
    
    def _ensure_directories(self):
        """创建所有必要的目录"""
        self.base_dir.mkdir(parents=True, exist_ok=True)
        for dir_name in self.TYPE_DIRS.values():
            (self.base_dir / dir_name).mkdir(parents=True, exist_ok=True)
    
    def _load_index(self) -> Dict[str, Any]:
        """加载索引文件"""
        if self.index_file.exists():
            try:
                with open(self.index_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load deliverable index: {e}")
        return {"deliverables": {}, "stats": {"total": 0, "by_type": {}}}
    
    def _save_index(self):
        """保存索引文件"""
        try:
            with open(self.index_file, 'w', encoding='utf-8') as f:
                json.dump(self.index, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save deliverable index: {e}")
    
    def _calculate_hash(self, content: str) -> str:
        """计算内容的 SHA256 哈希"""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()
    
    def store_deliverable(
        self,
        task_id: str,
        deliverable_type: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        存储交付物
        
        Args:
            task_id: 任务 ID
            deliverable_type: 交付物类型 (message/file/vote/payment/analysis/research/code/config)
            content: 交付物内容
            metadata: 额外元数据
        
        Returns:
            存储结果，包含路径、哈希、时间戳
        """
        if deliverable_type not in self.TYPE_DIRS:
            raise ValueError(f"Unknown deliverable type: {deliverable_type}")
        
        # 生成唯一 ID
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        deliverable_id = f"{task_id}_{deliverable_type}_{timestamp}"
        
        # 确定存储路径
        dir_name = self.TYPE_DIRS[deliverable_type]
        file_ext = self._get_file_extension(deliverable_type, content)
        file_path = self.base_dir / dir_name / f"{deliverable_id}{file_ext}"
        
        # 存储内容
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
        except Exception as e:
            logger.error(f"Failed to store deliverable: {e}")
            raise
        
        # 计算哈希
        content_hash = self._calculate_hash(content)
        
        # 构建记录
        record = {
            "id": deliverable_id,
            "task_id": task_id,
            "type": deliverable_type,
            "path": str(file_path),
            "hash": content_hash,
            "size": len(content.encode('utf-8')),
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {}
        }
        
        # 更新索引
        self.index["deliverables"][deliverable_id] = record
        self.index["stats"]["total"] += 1
        self.index["stats"]["by_type"][deliverable_type] = \
            self.index["stats"]["by_type"].get(deliverable_type, 0) + 1
        
        self._save_index()
        
        logger.info(f"Stored deliverable: {deliverable_id} ({len(content)} bytes)")
        
        return record
    
    def store_file_copy(
        self,
        task_id: str,
        source_path: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        复制文件到统一存储
        
        Args:
            task_id: 任务 ID
            source_path: 源文件路径
            metadata: 额外元数据
        
        Returns:
            存储结果
        """
        source = Path(source_path)
        if not source.exists():
            raise FileNotFoundError(f"Source file not found: {source_path}")
        
        # 读取文件内容
        with open(source, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 使用文件名作为元数据
        if metadata is None:
            metadata = {}
        metadata["original_path"] = str(source_path)
        metadata["original_name"] = source.name
        
        return self.store_deliverable(task_id, "file", content, metadata)
    
    def get_deliverable(self, deliverable_id: str) -> Optional[Dict[str, Any]]:
        """获取交付物记录"""
        return self.index["deliverables"].get(deliverable_id)
    
    def read_deliverable_content(self, deliverable_id: str) -> Optional[str]:
        """读取交付物内容"""
        record = self.get_deliverable(deliverable_id)
        if not record:
            return None
        
        try:
            with open(record["path"], 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            logger.error(f"Failed to read deliverable content: {e}")
            return None
    
    def list_deliverables(
        self,
        task_id: Optional[str] = None,
        deliverable_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        列出交付物
        
        Args:
            task_id: 按任务 ID 过滤
            deliverable_type: 按类型过滤
        
        Returns:
            交付物记录列表
        """
        results = []
        for record in self.index["deliverables"].values():
            if task_id and record["task_id"] != task_id:
                continue
            if deliverable_type and record["type"] != deliverable_type:
                continue
            results.append(record)
        
        # 按时间戳排序（最新优先）
        results.sort(key=lambda x: x["timestamp"], reverse=True)
        return results
    
    def verify_integrity(self, deliverable_id: str) -> Dict[str, Any]:
        """
        验证交付物完整性
        
        Returns:
            验证结果，包含是否通过、期望哈希、实际哈希
        """
        record = self.get_deliverable(deliverable_id)
        if not record:
            return {"valid": False, "reason": "Deliverable not found"}
        
        path = Path(record["path"])
        if not path.exists():
            return {"valid": False, "reason": "File not found"}
        
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            actual_hash = self._calculate_hash(content)
            expected_hash = record["hash"]
            
            return {
                "valid": actual_hash == expected_hash,
                "expected_hash": expected_hash,
                "actual_hash": actual_hash,
                "size": len(content.encode('utf-8'))
            }
        except Exception as e:
            return {"valid": False, "reason": str(e)}
    
    def get_stats(self) -> Dict[str, Any]:
        """获取存储统计信息"""
        return self.index["stats"]
    
    def delete_deliverable(self, deliverable_id: str) -> bool:
        """
        删除交付物（谨慎使用）
        
        注意：这不会删除实际文件，只从索引中移除。
        如需物理删除，请手动清理。
        """
        if deliverable_id not in self.index["deliverables"]:
            return False
        
        record = self.index["deliverables"][deliverable_id]
        deliverable_type = record["type"]
        
        # 从索引中移除
        del self.index["deliverables"][deliverable_id]
        self.index["stats"]["total"] -= 1
        self.index["stats"]["by_type"][deliverable_type] = \
            max(0, self.index["stats"]["by_type"].get(deliverable_type, 0) - 1)
        
        self._save_index()
        logger.info(f"Removed deliverable from index: {deliverable_id}")
        return True
    
    def _get_file_extension(self, deliverable_type: str, content: str) -> str:
        """根据交付物类型和内容确定文件扩展名"""
        extensions = {
            "message": ".json",
            "file": ".txt",  # 默认，可根据内容调整
            "vote": ".json",
            "payment": ".json",
            "analysis": ".md",
            "research": ".md",
            "code": ".py",  # 默认，可根据内容调整
            "config": ".json"
        }
        
        ext = extensions.get(deliverable_type, ".txt")
        
        # 智能检测代码文件类型
        if deliverable_type == "code":
            if content.strip().startswith("<?php"):
                ext = ".php"
            elif content.strip().startswith("#!/"):
                ext = ".sh"
            elif "def " in content or "class " in content:
                ext = ".py"
            elif "function " in content or "const " in content:
                ext = ".js"
        
        # 智能检测文件类型
        if deliverable_type == "file":
            if content.strip().startswith("#"):
                ext = ".md"
            elif content.strip().startswith("<?"):
                ext = ".php"
        
        return ext


# 全局单例
_store_instance: Optional[DeliverableStore] = None


def get_deliverable_store() -> DeliverableStore:
    """获取全局 DeliverableStore 实例"""
    global _store_instance
    if _store_instance is None:
        _store_instance = DeliverableStore()
    return _store_instance
