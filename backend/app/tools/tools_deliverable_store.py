"""
Tools for Deliverable Store - 成果物存储查询和审计接口

提供智能体可调用的工具函数，用于：
1. 查询已归档的交付物
2. 验证交付物完整性
3. 获取存储统计信息
4. 按任务 ID 检索交付物
"""

import json
import logging
from typing import Optional

try:
    from langchain_core.tools import tool
except ImportError:
    def tool(func):
        func.name = func.__name__
        return func

logger = logging.getLogger(__name__)


@tool
def list_archived_deliverables(
    task_id: Optional[str] = None,
    deliverable_type: Optional[str] = None
) -> str:
    """
    列出已归档的交付物
    
    Args:
        task_id: 按任务 ID 过滤（可选）
        deliverable_type: 按类型过滤（可选，可选值：file/message/vote/payment/analysis/research/code/config）
    
    Returns:
        交付物列表（JSON 格式）
    """
    try:
        from app.services.deliverable_store import get_deliverable_store
        store = get_deliverable_store()
        
        results = store.list_deliverables(task_id=task_id, deliverable_type=deliverable_type)
        
        if not results:
            return json.dumps({
                "status": "success",
                "count": 0,
                "deliverables": [],
                "message": "No deliverables found"
            }, ensure_ascii=False)
        
        # 格式化输出
        formatted = []
        for r in results:
            formatted.append({
                "id": r["id"],
                "task_id": r["task_id"],
                "type": r["type"],
                "path": r["path"],
                "hash": r["hash"][:16] + "...",
                "size": r["size"],
                "timestamp": r["timestamp"],
                "description": r.get("metadata", {}).get("deliverable_description", "")
            })
        
        return json.dumps({
            "status": "success",
            "count": len(formatted),
            "deliverables": formatted
        }, ensure_ascii=False, indent=2)
        
    except Exception as e:
        logger.error(f"list_archived_deliverables error: {e}")
        return json.dumps({"status": "error", "message": str(e)})


@tool
def verify_deliverable_integrity(deliverable_id: str) -> str:
    """
    验证交付物完整性（检查文件是否存在且未被篡改）
    
    Args:
        deliverable_id: 交付物 ID
    
    Returns:
        验证结果（JSON 格式）
    """
    try:
        from app.services.deliverable_store import get_deliverable_store
        store = get_deliverable_store()
        
        result = store.verify_integrity(deliverable_id)
        
        return json.dumps({
            "status": "success",
            "deliverable_id": deliverable_id,
            "valid": result.get("valid", False),
            "details": result
        }, ensure_ascii=False, indent=2)
        
    except Exception as e:
        logger.error(f"verify_deliverable_integrity error: {e}")
        return json.dumps({"status": "error", "message": str(e)})


@tool
def get_deliverable_store_stats() -> str:
    """
    获取成果物存储统计信息
    
    Returns:
        统计信息（JSON 格式）
    """
    try:
        from app.services.deliverable_store import get_deliverable_store
        store = get_deliverable_store()
        
        stats = store.get_stats()
        
        return json.dumps({
            "status": "success",
            "stats": stats
        }, ensure_ascii=False, indent=2)
        
    except Exception as e:
        logger.error(f"get_deliverable_store_stats error: {e}")
        return json.dumps({"status": "error", "message": str(e)})


@tool
def read_archived_deliverable(deliverable_id: str) -> str:
    """
    读取已归档交付物的内容
    
    Args:
        deliverable_id: 交付物 ID
    
    Returns:
        交付物内容
    """
    try:
        from app.services.deliverable_store import get_deliverable_store
        store = get_deliverable_store()
        
        content = store.read_deliverable_content(deliverable_id)
        
        if content is None:
            return json.dumps({
                "status": "error",
                "message": f"Deliverable {deliverable_id} not found or cannot be read"
            })
        
        record = store.get_deliverable(deliverable_id)
        
        return json.dumps({
            "status": "success",
            "deliverable_id": deliverable_id,
            "type": record["type"] if record else "unknown",
            "size": len(content),
            "content": content
        }, ensure_ascii=False, indent=2)
        
    except Exception as e:
        logger.error(f"read_archived_deliverable error: {e}")
        return json.dumps({"status": "error", "message": str(e)})


@tool
def get_task_deliverables_summary(task_id: str) -> str:
    """
    获取指定任务的所有交付物摘要
    
    Args:
        task_id: 任务 ID
    
    Returns:
        交付物摘要（JSON 格式）
    """
    try:
        from app.services.deliverable_store import get_deliverable_store
        store = get_deliverable_store()
        
        deliverables = store.list_deliverables(task_id=task_id)
        
        if not deliverables:
            return json.dumps({
                "status": "success",
                "task_id": task_id,
                "count": 0,
                "deliverables": [],
                "message": "No archived deliverables for this task"
            }, ensure_ascii=False)
        
        summary = []
        for d in deliverables:
            summary.append({
                "id": d["id"],
                "type": d["type"],
                "description": d.get("metadata", {}).get("deliverable_description", ""),
                "size": d["size"],
                "timestamp": d["timestamp"],
                "integrity": "✅" if d.get("hash") else "❓"
            })
        
        return json.dumps({
            "status": "success",
            "task_id": task_id,
            "count": len(summary),
            "deliverables": summary
        }, ensure_ascii=False, indent=2)
        
    except Exception as e:
        logger.error(f"get_task_deliverables_summary error: {e}")
        return json.dumps({"status": "error", "message": str(e)})
