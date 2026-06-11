# Weekly analysis wrapper for Windows Task Scheduler.
#
# Invoked by scripts/weekly_analyze.xml. Runs weekly_analyze.py against the
# standing run config and tees output to
# data/weekly_analyze_log/analyze_<ts>.log.
#
# This is the LLM/GPU job of the daily-ingestion cadence: it runs Qwen
# locally (Ollama) to aspect-tag the week's new mentions, then writes a
# per-week aggregate snapshot (no brief synthesis — that stays quarterly).
# Because it contends for the shared GPU, its schedule must NOT overlap the
# other project's nightly LLM run. Tagging is incremental + idempotent: the
# first run tags the whole untagged backlog (longest GPU session); every run
# after only tags that week's delta.
#
# This wrapper is path-relative; the XML carries the absolute placeholder paths.

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$LogDir = Join-Path $RepoRoot "data\weekly_analyze_log"
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}

$Ts = Get-Date -Format "yyyyMMdd_HHmmss"
$LogFile = Join-Path $LogDir "analyze_$Ts.log"
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$Script = Join-Path $RepoRoot "scripts\weekly_analyze.py"
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
