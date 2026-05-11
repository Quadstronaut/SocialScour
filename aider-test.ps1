# aider-test.ps1 - end-to-end smoke test of the local-model code-emission
# pipeline against a tiny PunyPython-style spec (2 files, ~60 LOC).
#
# Originally this drove aider.exe. Aider hangs indefinitely on Ollama's
# streaming endpoint on this Windows + non-TTY setup (the prompt_toolkit
# "No Windows console found" path), even with --no-stream / --no-pretty.
# Ollama itself is healthy (verified via direct curl: complete two-file
# emission in ~56s). So we drive Ollama directly via build-with-ollama.py.
#
# This script proves the end-to-end loop: spec -> local model -> files
# on disk -> code that runs and asserts correctness.

$ErrorActionPreference = 'Stop'

$Root    = 'P:\Documents\GIT\RedditScraper'
$Spec    = Join-Path $Root 'aider-test-spec.md'
$OutDir  = Join-Path $Root 'aider-test'
$Driver  = Join-Path $Root 'build-with-ollama.py'
$Model   = 'qwen3-coder:30b'

if (-not (Test-Path $Spec))   { throw "Spec not found: $Spec" }
if (-not (Test-Path $Driver)) { throw "Driver not found: $Driver" }

try {
    $r = Invoke-WebRequest -Uri 'http://localhost:11434/api/tags' -UseBasicParsing -TimeoutSec 3
    if ($r.StatusCode -ne 200) { throw "ollama returned $($r.StatusCode)" }
} catch {
    throw "Ollama not reachable at http://localhost:11434 - start it before running this script. ($_)"
}

# Wipe prior test artifacts so we measure THIS run.
if (Test-Path $OutDir) { Remove-Item -Recurse -Force -LiteralPath $OutDir }
New-Item -ItemType Directory -Path $OutDir | Out-Null

$targets = @(
    'aider-test/roman.py',
    'aider-test/test_roman.py'
)

$rawLog = Join-Path $Root "aider-test-raw-$(Get-Date -Format 'HHmmss').log"
$runLog = Join-Path $Root "aider-test-run-$(Get-Date -Format 'HHmmss').log"

Write-Host ''
Write-Host "[aider-test] root      : $Root"
Write-Host "[aider-test] spec      : $Spec"
Write-Host "[aider-test] driver    : $Driver"
Write-Host "[aider-test] model     : $Model  (num_ctx=32768)"
Write-Host "[aider-test] targets   : $($targets.Count) files"
Write-Host "[aider-test] run log   : $runLog"
Write-Host "[aider-test] raw log   : $rawLog"
Write-Host ''

$driverArgs = @(
    $Driver,
    '--spec', $Spec,
    '--root', $Root,
    '--model', $Model,
    '--num-ctx', '32768',
    '--raw-response', $rawLog
)
foreach ($t in $targets) { $driverArgs += @('--target', $t) }

Set-Location $Root
& python @driverArgs *> $runLog
$ec = $LASTEXITCODE
Get-Content $runLog | ForEach-Object { Write-Host $_ }
Write-Host ''
Write-Host "[aider-test] driver exit code: $ec" -ForegroundColor Cyan

if ($ec -ne 0) {
    Write-Host "[aider-test] DRIVER FAILED" -ForegroundColor Red
    exit 1
}

# --- File presence + smoke test --------------------------------------------
$romanPath = Join-Path $OutDir 'roman.py'
$testPath  = Join-Path $OutDir 'test_roman.py'
$ok = $true
foreach ($p in @($romanPath, $testPath)) {
    if (-not (Test-Path $p)) {
        Write-Host "[aider-test] MISSING: $p" -ForegroundColor Red
        $ok = $false
    } elseif ((Get-Item $p).Length -lt 50) {
        Write-Host "[aider-test] TOO SMALL: $p" -ForegroundColor Red
        $ok = $false
    } else {
        Write-Host "[aider-test] OK ($((Get-Item $p).Length) B): $p" -ForegroundColor Green
    }
}
if (-not $ok) { exit 1 }

Write-Host ''
Write-Host "[aider-test] running smoke test: python test_roman.py" -ForegroundColor Cyan
Push-Location $OutDir
try {
    $py = & python test_roman.py 2>&1
    $pyEc = $LASTEXITCODE
} finally {
    Pop-Location
}
$py | ForEach-Object { Write-Host "  $_" }
Write-Host "[aider-test] python exit: $pyEc"

if ($pyEc -eq 0 -and (($py -join "`n") -match 'OK')) {
    Write-Host ''
    Write-Host "[aider-test] END-TO-END PASS" -ForegroundColor Green
    exit 0
} else {
    Write-Host ''
    Write-Host "[aider-test] END-TO-END FAIL" -ForegroundColor Red
    exit 1
}
