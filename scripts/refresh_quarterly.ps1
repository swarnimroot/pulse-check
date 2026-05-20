# Quarterly refresh dry-run wrapper for Windows Task Scheduler.
#
# Invoked by scripts/refresh_quarterly.xml. Runs refresh.py in dry-run mode
# (no --execute flag) and tees output to data/refresh_log/dryrun_<ts>.log
# so the scheduled-job verdict is reviewable after the fact.
#
# The scheduler intentionally NEVER fires --execute (per session-39 lock):
# the operator reads the dry-run log, then manually runs:
#     .venv\Scripts\python.exe scripts\refresh.py --execute
#
# This wrapper is path-relative; the XML carries the absolute placeholder paths.

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$LogDir = Join-Path $RepoRoot "data\refresh_log"
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}

$Ts = Get-Date -Format "yyyyMMdd_HHmmss"
$LogFile = Join-Path $LogDir "dryrun_$Ts.log"
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$Script = Join-Path $RepoRoot "scripts\refresh.py"

Set-Location $RepoRoot
& $Python $Script *>&1 | Tee-Object -FilePath $LogFile
exit $LASTEXITCODE
