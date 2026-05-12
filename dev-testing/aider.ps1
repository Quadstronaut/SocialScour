# aider.ps1 - non-interactive run that executes build-prompt.md against a
# local Ollama model and writes the resulting files under aider/.
#
# Originally this script invoked aider.exe. On this Windows + non-TTY setup
# aider.exe hangs indefinitely on Ollama's chat endpoint (the prompt_toolkit
# "No Windows console found" path bricks something downstream). Ollama
# itself is healthy. So we drive Ollama directly via build-with-ollama.py,
# which does what aider was doing here: prompt the model in whole-file
# format, parse the fenced blocks, and write each to disk.
#
# The aider/ subfolder name and the script name are kept the same so this
# slot in the agent comparison harness still refers to the same artifact
# layout as goose/, opencode/, etc.

$ErrorActionPreference = 'Stop'

$Root    = 'P:\Documents\GIT\RedditScraper'
$Spec    = Join-Path $Root 'build-prompt.md'
$OutDir  = Join-Path $Root 'aider'
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

# Move to the git root BEFORE wiping, otherwise the wipe fails if the
# parent shell happened to be inside aider/.
Set-Location $Root

# Empty aider/ so a previous partial run does not pollute this one. We
# delete the *contents* (not the dir itself) because some shell may hold a
# handle on aider/ as its cwd and refuse to let us remove the dir.
if (Test-Path $OutDir) {
    Get-ChildItem -LiteralPath $OutDir -Force | ForEach-Object {
        Remove-Item -Recurse -Force -LiteralPath $_.FullName
    }
} else {
    New-Item -ItemType Directory -Path $OutDir | Out-Null
}

$targets = @(
    'aider/pyproject.toml',
    'aider/README.md',
    'aider/reddit_scraper/__init__.py',
    'aider/reddit_scraper/schema.py',
    'aider/reddit_scraper/fetch.py',
    'aider/reddit_scraper/summarize.py',
    'aider/reddit_scraper/render.py',
    'aider/reddit_scraper/cli.py',
    'aider/reddit_scraper/mcp_server.py'
)

$ts     = Get-Date -Format 'HHmmss'
$runLog = Join-Path $Root "aider-run-$ts.log"
$rawLog = Join-Path $Root "aider-raw-$ts.log"

Write-Host ''
Write-Host "[aider] root      : $Root"
Write-Host "[aider] spec      : $Spec"
Write-Host "[aider] driver    : $Driver"
Write-Host "[aider] model     : $Model  (num_ctx=32768)"
Write-Host "[aider] targets   : $($targets.Count) files"
Write-Host "[aider] run log   : $runLog"
Write-Host "[aider] raw log   : $rawLog"
Write-Host ''

$driverArgs = @(
    $Driver,
    '--spec', $Spec,
    '--root', $Root,
    '--model', $Model,
    '--num-ctx', '32768',
    '--retries', '2',
    '--timeout', '1200',
    '--raw-response', $rawLog
)
foreach ($t in $targets) { $driverArgs += @('--target', $t) }

& python @driverArgs *> $runLog
$ec = $LASTEXITCODE
Get-Content $runLog | ForEach-Object { Write-Host $_ }
Write-Host ''
Write-Host "[aider] driver exit code: $ec" -ForegroundColor Cyan
exit $ec
