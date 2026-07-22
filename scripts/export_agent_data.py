#!/usr/bin/env python3
"""
Bit Politeia Agent Data & Identity Export Script
================================================
Exports agent identity keys, sessions history, memory databases,
resident code files, governance data, and frontend state snapshot
into a unified zip bundle for seamless migration across hosts.

Usage:
    python scripts/export_agent_data.py [--output my_backup.zip] [--include-logs]
"""

import argparse
import hashlib
import json
import os
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


def generate_frontend_state_snapshot(project_root: Path) -> dict:
    """Generate a frontend LocalStorage state snapshot from backend configs and keys."""
    snapshot = {
        "bp_onboarded": "true",
        "bp_api_url": "http://localhost:8100",
    }

    # Load agent_config.json if present
    agent_cfg_path = project_root / "agent_config.json"
    if agent_cfg_path.exists():
        try:
            with open(agent_cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                snapshot["bp_name"] = cfg.get("name", "Aarron")
                snapshot["bp_personality"] = cfg.get("personality", "Professional")
                snapshot["bp_verbose_llm"] = str(cfg.get("verbose_llm", True)).lower()
                snapshot["bp_bootstrap_verify"] = str(cfg.get("bootstrap_verify", False)).lower()
                snapshot["bp_p2p_reply_delay"] = str(cfg.get("p2p_reply_delay", 10))
                snapshot["bp_agent_language"] = cfg.get("agent_language", "中文")
                snapshot["bp_ralph_wiggum_mode"] = str(cfg.get("ralph_wiggum_mode", False)).lower()
                snapshot["bp_field"] = cfg.get("research_field", "feeding motivation neuroscience")
        except Exception as e:
            print(f"⚠️ Warning reading agent_config.json for frontend snapshot: {e}")

    # Load keys if present
    pub_key_path = project_root / "keys" / "public_key.pem"
    priv_key_path = project_root / "keys" / "private_key.pem"

    if pub_key_path.exists():
        try:
            snapshot["bp_public_key"] = pub_key_path.read_text(encoding="utf-8").strip()
        except Exception:
            pass

    if priv_key_path.exists():
        try:
            snapshot["bp_private_key"] = priv_key_path.read_text(encoding="utf-8").strip()
        except Exception:
            pass

    return snapshot


def export_data(output_path: str = None, include_logs: bool = False) -> str:
    project_root = Path(__file__).resolve().parent.parent

    if not output_path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = f"bit_politeia_backup_{timestamp}.zip"

    output_file = Path(output_path).resolve()

    print("==================================================")
    print("🚀 Starting Bit Politeia Agent Data & Identity Export")
    print(f"📍 Project Root: {project_root}")
    print(f"📦 Target Output Archive: {output_file}")
    print("==================================================")

    # 1. Gather files to package
    files_to_pack = []  # list of (abs_path, arcname)

    # A. Root config files & keys
    root_configs = [".env", "agent_config.json", "resident_memory.json"]
    for cfg in root_configs:
        p = project_root / cfg
        if p.exists():
            files_to_pack.append((p, cfg))

    keys_dir = project_root / "keys"
    if keys_dir.exists():
        for item in keys_dir.rglob("*"):
            if item.is_file():
                rel = item.relative_to(project_root)
                files_to_pack.append((item, str(rel)))

    # B. Backend data directory (backend/data/)
    backend_data_dir = project_root / "backend" / "data"
    if backend_data_dir.exists():
        for item in backend_data_dir.rglob("*"):
            if item.is_file():
                rel = item.relative_to(project_root)
                rel_str = str(rel)

                # Ignore logs if not requested
                if not include_logs and ("backend/data/logs" in rel_str or rel_str.endswith(".log")):
                    continue
                # Ignore temp locks
                if ".locks" in rel_str:
                    continue

                files_to_pack.append((item, rel_str))

    # C. Resident data directory (data/)
    root_data_dir = project_root / "data"
    if root_data_dir.exists():
        for item in root_data_dir.rglob("*"):
            if item.is_file():
                rel = item.relative_to(project_root)
                rel_str = str(rel)

                if not include_logs and ("data/logs" in rel_str or rel_str.endswith(".log")):
                    continue

                files_to_pack.append((item, rel_str))

    print(f"📋 Collected {len(files_to_pack)} file items for packaging...")

    # 2. Write Zip Archive
    with zipfile.ZipFile(output_file, "w", zipfile.ZIP_DEFLATED) as zipf:
        for abs_path, arcname in files_to_pack:
            try:
                zipf.write(abs_path, arcname)
            except FileNotFoundError:
                # Ignore transient files deleted mid-export (e.g. temporary log files)
                continue

        # Append synthetic frontend state snapshot
        frontend_snapshot = generate_frontend_state_snapshot(project_root)
        snapshot_json_str = json.dumps(frontend_snapshot, indent=2, ensure_ascii=False)
        zipf.writestr("frontend_state_backup.json", snapshot_json_str)

        # Append manifest
        manifest = {
            "exported_at": datetime.now().isoformat(),
            "file_count": len(files_to_pack) + 1,
            "included_logs": include_logs,
            "version": "1.0.0",
        }
        zipf.writestr("export_manifest.json", json.dumps(manifest, indent=2))

    # 3. Output Checksum and Summary
    file_size_mb = output_file.stat().st_size / (1024 * 1024)
    sha256 = calculate_file_hash(str(output_file))

    print("\n✅ Export Completed Successfully!")
    print(f"📁 Archive Path: {output_file}")
    print(f"📊 Archive Size: {file_size_mb:.2f} MB")
    print(f"🔒 SHA256 Checksum: {sha256}")
    print("==================================================")

    return str(output_file)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export Bit Politeia Agent Data & Identity")
    parser.add_argument("--output", "-o", help="Target zip file path", default=None)
    parser.add_argument("--include-logs", action="store_true", help="Include system log files in export archive")

    args = parser.parse_args()
    export_data(output_path=args.output, include_logs=args.include_logs)
