#!/usr/bin/env python3
"""
Bit Politeia Agent Data & Identity Import Script
================================================
Imports agent identity keys, sessions history, memory databases,
resident code files, governance data, and frontend state snapshot
from a backup zip bundle into the current Bit Politeia deployment.

Generates `frontend_restore_helper.html` to allow 1-click restoration
of Web UI LocalStorage (keys, onboarded state, preferences).

Usage:
    python scripts/import_agent_data.py --input bit_politeia_backup_20260722.zip [--force]
"""

import argparse
import hashlib
import json
import os
import shutil
import sys
import zipfile
from datetime import datetime
from pathlib import Path


def calculate_file_hash(filepath: str) -> str:
    """Calculate SHA256 checksum of a file."""
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(65536), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def generate_frontend_restore_html(frontend_state: dict, output_file: Path):
    """Generate a standalone HTML file that allows 1-click LocalStorage restoration."""
    json_data_js = json.dumps(frontend_state, indent=2, ensure_ascii=False)

    html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>Bit Politeia - 前端身份与设置恢复助手</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background-color: #0f172a;
            color: #f8fafc;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            margin: 0;
        }}
        .card {{
            background-color: #1e293b;
            border: 1px solid #334155;
            border-radius: 12px;
            padding: 32px;
            max-width: 520px;
            width: 90%;
            box-shadow: 0 10px 25px rgba(0, 0, 0, 0.5);
            text-align: center;
        }}
        h1 {{
            color: #38bdf8;
            font-size: 24px;
            margin-bottom: 8px;
        }}
        p {{
            color: #94a3b8;
            font-size: 14px;
            line-height: 1.6;
        }}
        .badge {{
            display: inline-block;
            background-color: #0369a1;
            color: #e0f2fe;
            padding: 4px 12px;
            border-radius: 9999px;
            font-size: 12px;
            font-weight: 600;
            margin-bottom: 20px;
        }}
        .btn {{
            background: linear-gradient(135deg, #0284c7, #2563eb);
            color: white;
            border: none;
            padding: 12px 24px;
            font-size: 16px;
            font-weight: 600;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.2s ease;
            width: 100%;
            margin-top: 16px;
        }}
        .btn:hover {{
            background: linear-gradient(135deg, #0369a1, #1d4ed8);
            transform: translateY(-1px);
        }}
        .status {{
            margin-top: 20px;
            padding: 12px;
            border-radius: 6px;
            font-size: 14px;
            display: none;
        }}
        .status.success {{
            background-color: #064e3b;
            color: #6ee7b7;
            display: block;
        }}
        code {{
            background-color: #0f172a;
            padding: 2px 6px;
            border-radius: 4px;
            font-family: monospace;
            color: #38bdf8;
        }}
    </style>
</head>
<body>
    <div class="card">
        <span class="badge">Bit Politeia 部署迁移助手</span>
        <h1>恢复前端身份与全局设置</h1>
        <p>此工具会将导出的智能体公私钥对、网络身份以及偏好设置还原至当前浏览器的 LocalStorage 中。</p>
        
        <button class="btn" onclick="restoreLocalStorage()">🚀 一键写入 LocalStorage 并恢复身份</button>
        
        <div id="status" class="status"></div>
    </div>

    <script>
        const stateData = {json_data_js};

        function restoreLocalStorage() {{
            try {{
                let count = 0;
                for (const [key, value] of Object.entries(stateData)) {{
                    if (value !== null && value !== undefined) {{
                        localStorage.setItem(key, String(value));
                        count++;
                    }}
                }}
                const statusEl = document.getElementById('status');
                statusEl.className = 'status success';
                statusEl.innerHTML = '✅ 成功恢复 ' + count + ' 项前端设置与身份秘钥！<br>请直接刷新或打开 <a href="http://localhost:3000" style="color:#38bdf8">Web 控制台 (http://localhost:3000)</a> 即可进入恢复状态。';
            }} catch (err) {{
                alert('写入 LocalStorage 失败: ' + err.message);
            }}
        }}
    </script>
</body>
</html>
"""
    output_file.write_text(html_content, encoding="utf-8")


def import_data(input_path: str, checksum: str = None, force: bool = False) -> bool:
    project_root = Path(__file__).resolve().parent.parent
    input_file = Path(input_path).resolve()

    if not input_file.exists():
        print(f"❌ Error: Backup archive not found at '{input_file}'")
        return False

    print("==================================================")
    print("🚀 Starting Bit Politeia Agent Data & Identity Import")
    print(f"📍 Target Location: {project_root}")
    print(f"📦 Source Archive: {input_file}")
    print("==================================================")

    # 1. Verify SHA256 if provided
    actual_hash = calculate_file_hash(str(input_file))
    print(f"🔒 Source Archive Checksum: {actual_hash}")
    if checksum:
        if checksum.strip().lower() != actual_hash.lower():
            print(f"❌ Error: SHA256 Checksum mismatch!\nExpected: {checksum}\nActual:   {actual_hash}")
            if not force:
                return False
        else:
            print("✅ SHA256 Checksum verified!")

    # 2. Check Archive Validity & Manifest
    try:
        with zipfile.ZipFile(input_file, "r") as zipf:
            namelist = zipf.namelist()
            if "export_manifest.json" in namelist:
                manifest_data = json.loads(zipf.read("export_manifest.json").decode("utf-8"))
                print(f"📄 Manifest Found — Exported at: {manifest_data.get('exported_at')}")

            # 3. Create Safety Backup of current deployment
            backup_dir = project_root / ".backup_before_import"
            print(f"🛡️ Creating safety backup of current state in '{backup_dir}'...")

            if (project_root / "backend" / "data").exists():
                shutil.copytree(
                    project_root / "backend" / "data",
                    backup_dir / "backend_data",
                    dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("*.log"),
                )

            # 4. Extract Package Files
            print("📥 Extracting archive files...")
            for member in zipf.infolist():
                if member.filename in ["export_manifest.json", "frontend_state_backup.json"]:
                    continue

                target_path = project_root / member.filename
                # Ensure directory exists
                if member.is_dir():
                    target_path.mkdir(parents=True, exist_ok=True)
                else:
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    with zipf.open(member) as source, open(target_path, "wb") as target:
                        shutil.copyfileobj(source, target)

            # 5. Handle Frontend State Restoration Helper
            if "frontend_state_backup.json" in namelist:
                frontend_state = json.loads(zipf.read("frontend_state_backup.json").decode("utf-8"))
                helper_html_path = project_root / "frontend_restore_helper.html"
                generate_frontend_restore_html(frontend_state, helper_html_path)
                print(f"\n🌐 Generated Frontend LocalStorage Helper: {helper_html_path}")

            # 6. Count Resident Files
            resident_dir = project_root / "data" / "resident"
            resident_count = len([f for f in resident_dir.rglob("*") if f.is_file()]) if resident_dir.exists() else 0

    except Exception as e:
        print(f"❌ Error extracting backup archive: {e}")
        return False

    print("\n✅ Import Completed Successfully!")
    print("==================================================")
    print(f"📁 Restored Resident Artifacts (data/resident/): {resident_count} files")
    print("💡 NEXT STEPS:")
    print("1. Start Bit Politeia backend service (Port 8100):")
    print("   nohup python backend/main.py > backend/data/logs/cron.log 2>&1 &")
    print("2. Open http://localhost:3000 in your browser. The Web Console will automatically detect your active backend node and bypass the onboarding setup.")
    print("==================================================")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import Bit Politeia Agent Data & Identity")
    parser.add_argument("--input", "-i", required=True, help="Path to input backup zip archive")
    parser.add_argument("--checksum", "-c", help="Expected SHA256 checksum for verification", default=None)
    parser.add_argument("--force", "-f", action="store_true", help="Force import even if checksum fails")

    args = parser.parse_args()
    import_data(input_path=args.input, checksum=args.checksum, force=args.force)
