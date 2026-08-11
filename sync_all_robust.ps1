
$source = "d:\BaiduSyncdisk\SIAT\coding\bit_politeia"
$dest = "D:\git\bit_politeia"

$files = @(
    "backend\app\services\agent_service.py",
    "backend\app\services\bootstrap_service.py",
    "backend\app\services\bootstrap_storage.py",
    "backend\app\services\p2p_server.py",
    "backend\app\agent\context.py",
    "backend\app\agent\tools.py",
    "backend\app\agent\prompts.py",
    "backend\app\agent\pipeline.py",
    "task.md",
    "walkthrough.md"
)

$dirs = @(
    "backend\skills\long-doc-analyzer",
    "docs",
    "tests"
)

Write-Host "Starting Robust Sync..."

# Sync Files
foreach ($file in $files) {
    $srcPath = Join-Path $source $file
    $destPath = Join-Path $dest $file
    
    # Ensure dest dir exists
    $destDir = Split-Path $destPath -Parent
    if (-not (Test-Path $destDir)) {
        New-Item -ItemType Directory -Force -Path $destDir | Out-Null
    }

    if (Test-Path $srcPath) {
        Write-Host "Copying $file..."
        Copy-Item $srcPath -Destination $destPath -Force
        
        # Verify
        if (Test-Path $destPath) {
             # Check modified time or size to be sure? 
             # Just checking existence for now.
             Write-Host "Verified: $destPath exists."
        } else {
             Write-Error "FAILED to copy $file"
        }
    } else {
        Write-Error "Source file not found: $srcPath"
    }
}

# Sync Dirs
foreach ($dir in $dirs) {
    $srcPath = Join-Path $source $dir
    $destPath = Join-Path $dest $dir
    
    if (Test-Path $srcPath) {
        Write-Host "Copying Directory $dir..."
        if (-not (Test-Path $destPath)) {
            New-Item -ItemType Directory -Force -Path $destPath | Out-Null
        }
        Copy-Item $srcPath\* -Destination $destPath -Recurse -Force
        
        # Verify
        if (Test-Path $destPath) {
             Write-Host "Verified: $destPath exists."
        } else {
             Write-Error "FAILED to copy directory $dir"
        }
    } else {
        Write-Error "Source directory not found: $srcPath"
    }
}

Write-Host "Robust Sync Complete."
