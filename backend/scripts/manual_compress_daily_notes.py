#!/usr/bin/env python
"""
手动触发 Daily Notes 压缩脚本。

用于：
1. 为已归档的旧文件生成摘要
2. 压缩当前待处理的旧笔记
"""

import asyncio
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import os

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from app.services.memory_store import MemoryStore


async def summarize_archived_notes(ms: MemoryStore, llm: ChatOpenAI) -> None:
    """为已归档但没有摘要的文件生成摘要。"""
    archived_files = sorted(ms.archive_dir.glob("*.md"), reverse=True)

    if not archived_files:
        print("没有已归档的文件")
        return

    print(f"=== 处理已归档文件 ({len(archived_files)} 个) ===")

    # Read all archived files
    notes = []
    for f in archived_files:
        try:
            date_str = f.stem
            content = f.read_text(encoding="utf-8")
            notes.append((date_str, content, f))
            print(f"  读取: {date_str} ({len(content)} 字符)")
        except Exception as e:
            print(f"  错误: {f.name} - {e}")

    if not notes:
        return

    # Generate summary
    print("\n生成摘要...")
    summary = await generate_summary(llm, notes)

    if summary:
        # Write summary
        header = "# Daily Notes 历史摘要\n\n此文件包含已压缩的历史 Daily Notes 摘要。\n原始文件已归档至 `archive/` 目录。\n\n"
        ms.summary_file.write_text(header + summary, encoding="utf-8")
        print(f"摘要已保存: {len(summary)} 字符")
    else:
        print("摘要生成失败")


async def compress_current_notes(ms: MemoryStore, llm: ChatOpenAI) -> None:
    """压缩当前待处理的旧笔记。"""
    old_notes = ms.get_old_daily_notes(before_days=3)

    if not old_notes:
        print("没有待压缩的笔记")
        return

    print(f"\n=== 处理待压缩笔记 ({len(old_notes)} 个) ===")

    for date_str, content, path in old_notes:
        print(f"  待压缩: {date_str} ({len(content)} 字符)")

    # Generate summary
    print("\n生成摘要...")
    summary = await generate_summary(llm, old_notes)

    if summary:
        # Append to existing summary
        existing = ms.read_summary()
        date_range = f"{old_notes[0][0]} ~ {old_notes[-1][0]}"
        new_section = f"\n\n---\n### 摘要范围: {date_range}\n压缩日期: {ms._get_today_date()}\n原始文件数: {len(old_notes)}\n\n{summary}"

        if existing:
            ms.summary_file.write_text(existing + new_section, encoding="utf-8")
        else:
            header = "# Daily Notes 历史摘要\n\n此文件包含已压缩的历史 Daily Notes 摘要。\n原始文件已归档至 `archive/` 目录。\n\n"
            ms.summary_file.write_text(header + new_section, encoding="utf-8")

        print(f"摘要已追加: +{len(summary)} 字符")

        # Archive original files
        for date_str, content, path in old_notes:
            ms.archive_daily_note(path)
            print(f"  已归档: {date_str}")

        print(f"\n压缩完成: {len(old_notes)} 个文件")
    else:
        print("摘要生成失败，跳过归档")


async def generate_summary(llm: ChatOpenAI, notes: list[tuple[str, str, Path]]) -> str:
    """使用 LLM 生成结构化摘要。"""
    if not notes:
        return ""

    # Combine notes with date headers
    notes_text = ""
    total_chars = 0
    max_chars = 50000

    for date_str, content, _ in notes:
        section = f"\n## {date_str}\n{content}\n"
        if total_chars + len(section) > max_chars:
            notes_text += f"\n## {date_str}\n[内容过长已截断，请查看归档文件]\n"
            break
        notes_text += section
        total_chars += len(section)

    prompt = f"""
请对以下历史 Daily Notes 进行结构化压缩摘要。

要求：
1. **提取关键信息**：重要决策、经验教训、未完成任务
2. **保留具体细节**：如错误信息、配置参数、文件路径等
3. **按主题归类**：相同主题的内容合并
4. **标注时间**：保留原始日期信息

输出格式（Markdown）：
```
### [主题/日期范围]

**关键决策**:
- ...

**经验教训**:
- ...

**未完成任务**:
- ...

**技术细节**:
- ...
```

---

{notes_text}

---
请生成压缩摘要：
"""

    try:
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        return response.content.strip()
    except Exception as e:
        print(f"LLM 错误: {e}")
        # Fallback: extract headers
        fallback = ""
        for date_str, content, _ in notes:
            headers = [line for line in content.split("\n") if line.strip().startswith("#")]
            if headers:
                fallback += f"**{date_str}**:\n" + "\n".join(headers[:5]) + "\n\n"
        return fallback


async def main():
    # Initialize
    ms = MemoryStore()

    # Initialize LLM
    base_url = os.getenv("AUX_MODEL_URL", os.getenv("OPENAI_BASE_URL", "http://localhost:11434/v1"))
    api_key = os.getenv("AUX_MODEL_KEY", os.getenv("OPENAI_API_KEY", "sk-dummy"))
    model = os.getenv("AUX_MODEL_NAME", os.getenv("OPENAI_MODEL", "llama3.1:8b"))

    llm = ChatOpenAI(
        base_url=base_url,
        api_key=api_key,
        model=model,
        temperature=0.3,
        max_tokens=2000,
    )

    print(f"LLM 配置: {model} @ {base_url}")
    print(f"内存目录: {ms.memory_dir}")
    print(f"摘要文件: {ms.summary_file}")

    # Step 1: Summarize archived files (if no summary exists)
    existing_summary = ms.read_summary()
    if not existing_summary:
        await summarize_archived_notes(ms, llm)
    else:
        print(f"已有摘要 ({len(existing_summary)} 字符)，跳过归档文件处理")

    # Step 2: Compress current pending notes
    await compress_current_notes(ms, llm)

    # Final status
    print("\n=== 最终状态 ===")
    final_summary = ms.read_summary()
    print(f"摘要文件大小: {len(final_summary)} 字符 ({len(final_summary) / 1024:.1f} KB)")

    archived_count = len(list(ms.archive_dir.glob("*.md")))
    print(f"归档文件数: {archived_count}")

    remaining_count = len(ms.get_old_daily_notes(before_days=3))
    print(f"剩余待压缩: {remaining_count}")


if __name__ == "__main__":
    asyncio.run(main())
