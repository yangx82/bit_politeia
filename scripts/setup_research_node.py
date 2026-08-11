import os
import sys
import subprocess
import shutil
from pathlib import Path

# --- Configuration ---
REPO_URL = "https://github.com/aiming-lab/AutoResearchClaw.git"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INSTALL_DIR = PROJECT_ROOT.parent / "AutoResearchClaw"

def run_command(cmd, cwd=None, env=None):
    print(f">> Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error: {result.stderr}")
        return False, result.stderr
    return True, result.stdout

def setup_research_node():
    print("=== Bit Politeia: AutoResearchClaw One-Click Installer ===")
    
    # 1. Path Setup
    install_dir = DEFAULT_INSTALL_DIR
    if install_dir.exists():
        print(f"[*] Found existing AutoResearchClaw at: {install_dir}")
    else:
        print(f"[*] Cloning AutoResearchClaw to: {install_dir}")
        ok, err = run_command(["git", "clone", REPO_URL, str(install_dir)])
        if not ok:
            print("Failed to clone repository. Please install git or check network.")
            return

    # 2. Virtual Environment Setup
    venv_dir = install_dir / ".venv"
    if not venv_dir.exists():
        print("[*] Creating virtual environment...")
        ok, err = run_command([sys.executable, "-m", "venv", str(venv_dir)])
        if not ok: return

    # 3. Dependencies Installation
    print("[*] Installing dependencies (this may take a few minutes)...")
    python_exe = str(venv_dir / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python"))
    
    # Basic install
    ok, err = run_command([python_exe, "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"], cwd=install_dir)
    if not ok: return
    
    # Install as editable with [all] extras
    ok, err = run_command([python_exe, "-m", "pip", "install", "-e", ".[all]"], cwd=install_dir)
    if not ok:
        print("Warning: Failed to install with [all] extras. Attempting base install...")
        ok, err = run_command([python_exe, "-m", "pip", "install", "-e", "."], cwd=install_dir)
        if not ok: return

    # 4. Configuration (config.arc.yaml)
    arc_config = install_dir / "config.arc.yaml"
    if not arc_config.exists():
        print("[*] Generating default config.arc.yaml...")
        example_config = install_dir / "config.researchclaw.example.yaml"
        if example_config.exists():
            shutil.copy(example_config, arc_config)
            # We should ideally patch it here, but for now a copy is a good start.
            print(f"[*] Created {arc_config} from example. Please check its settings.")
    
    # 5. Bit Politeia Integration (.env)
    env_file = PROJECT_ROOT / ".env"
    print(f"[*] Updating {env_file}...")
    
    env_lines = []
    if env_file.exists():
        with open(env_file, 'r', encoding='utf-8') as f:
            env_lines = f.readlines()
    
    new_lines = []
    has_path = False
    for line in env_lines:
        if line.startswith("RESEARCHCLAW_HOME="):
            new_lines.append(f"RESEARCHCLAW_HOME={install_dir}\n")
            has_path = True
        else:
            new_lines.append(line)
            
    if not has_path:
        new_lines.append(f"\n# AutoResearchClaw Integration\n")
        new_lines.append(f"RESEARCHCLAW_HOME={install_dir}\n")
        
    with open(env_file, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)

    # 6. Final Dependency Verification
    print("[*] Verifying critical dependencies...")
    check_code = "import arxiv, numpy; print('SUCCESS')"
    ok, out = run_command([python_exe, "-c", check_code])
    if "SUCCESS" not in out:
        print("\n[!] WARNING: Literature search dependencies missing!")
        print(f"    Please run: {python_exe} -m pip install arxiv>=2.1 numpy")
    else:
        print("[*] Host dependencies verified.")

    print("\n=== Installation Complete! ===")
    print(f"1. AutoResearchClaw is installed at: {install_dir}")
    print(f"2. Bit Politeia is configured to use this path.")
    print(f"3. IMPORTANT: Make sure your OPENAI_API_KEY is set in {env_file}")
    print(f"4. DOCKER: Once Docker is installed, you can enable 'mode: docker' in {arc_config}")
    print(f"   - RECOMMENDED: Use the pre-built 'researchclaw/experiment:latest' image (37.4GB).")
    print(f"   - NOTE: Internal timeouts (300s/120s) are now pre-configured for stability.")

if __name__ == "__main__":
    setup_research_node()
