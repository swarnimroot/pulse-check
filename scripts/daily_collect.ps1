# Daily ingestion collector wrapper for Windows Task Scheduler.
#
# Invoked by scripts/daily_collect.xml. Runs daily_collect.py against the
# standing run config and tees output to
# data/daily_collect_log/collect_<ts>.log so each night's collection +
# gap-detection verdict is reviewable after the fact.
#
# Unlike the quarterly wrapper (which is dry-run only because it fires paid
# LLM work), this wrapper RUNS the collection directly: daily collect is
# scrape-only (no LLM, no GPU) and idempotent (dedup at ingest by mention_id),
# so an unattended nightly run is safe to auto-execute. State is written only
# on success, so a crash mid-scrape leaves the gap reported on the next run.
#
# This wrapper is path-relative; the XML carries the absolute placeholder paths.

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$LogDir = Join-Path $RepoRoot "data\daily_collect_log"
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}

$Ts = Get-Date -Format "yyyyMMdd_HHmmss"
$LogFile = Join-Path $LogDir "collect_$Ts.log"
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$Script = Join-Path $RepoRoot "scripts\daily_collect.py"
$RunConfig = Join-Path $RepoRoot "configs\run_wave5_v1.yaml"

# PowerShell 5.1 wraps each stderr line from a native exe as a NativeCommandError
# ErrorRecord. With ErrorActionPreference=Stop the first such line aborts the
# wrapper before any work runs — and Python logs to stderr, so the cold-start
# line would trip it immediately. Switch to Continue and treat the process exit
# code ($LASTEXITCODE) as the source of truth instead.
$ErrorActionPreference = "Continue"
Set-Location $RepoRoot
& $Python $Script --run-config $RunConfig *>&1 | Tee-Object -FilePath $LogFile
exit $LASTEXITCODE
