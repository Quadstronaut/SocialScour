# goose.ps1 - non-interactive goose run against build-prompt.md inside goose/
# Two fixes vs the interactive approach:
#   1. Inline the full spec content into the instructions so the model never
#      has to call a read tool (qwen3-coder hallucinates tool names like READ).
#   2. Use `goose run --instructions <file>` instead of `goose session` to
#      bypass the TUI's broken multi-line paste handling on Windows ConPTY.
# Reality check: tool-call agents like goose are still flaky on a 30B local
# model. If this misbehaves it's a model-vs-tool-schema problem, not goose.

$ErrorActionPreference = 'Stop'

$Root        = 'P:\Documents\GIT\RedditScraper'
$Spec        = Join-Path $Root 'build-prompt.md'
$AgentDir    = Join-Path $Root 'goose'
$AgentName   = 'goose'
$GooseExe    = 'C:\Users\Quadstronaut\scoop\shims\goose.exe'
$SessionName = "reddit-scraper-build-$(Get-Date -Format 'yyyyMMdd-HHmm')"

if (-not (Test-Path $Spec))     { throw "Spec not found: $Spec" }
if (-not (Test-Path $AgentDir)) { throw "Agent dir not found: $AgentDir" }
if (-not (Test-Path $GooseExe)) { throw "goose.exe not found: $GooseExe" }

try {
    $r = Invoke-WebRequest -Uri 'http://localhost:11434/api/tags' -UseBasicParsing -TimeoutSec 3
    if ($r.StatusCode -ne 200) { throw "ollama returned $($r.StatusCode)" }
} catch {
    throw "Ollama not reachable at http://localhost:11434 - start it before running this script. ($_)"
}

$specContent = Get-Content -Raw -LiteralPath $Spec
$instructions = @"
You are working in the current directory: $AgentDir
The git repo root is: $Root
Filesystem MCP is rooted at P:\Documents\GIT - use absolute paths under that root for any file operation.

Execute the spec below inside the current working directory ($AgentDir). Build every file the spec lists. After each major file (pyproject.toml, schema.py, fetch.py, summarize.py, render.py, cli.py, mcp_server.py) commit via the shell with message "$($AgentName): <file>". Stop after the acceptance check passes.

Do NOT call any tool to read the spec - it is inlined below in full.

===== BEGIN build-prompt.md =====
$specContent
===== END build-prompt.md =====
"@

$instructionsFile = Join-Path $env:TEMP "goose-instructions-$(Get-Date -Format 'yyyyMMdd-HHmmss').md"
Set-Content -LiteralPath $instructionsFile -Value $instructions -Encoding UTF8

Write-Host ""
Write-Host "[$AgentName] cwd          : $AgentDir"
Write-Host "[$AgentName] session      : $SessionName"
Write-Host "[$AgentName] instructions : $instructionsFile"
Write-Host "[$AgentName] model        : qwen3-coder:30b via ollama (from goose config.yaml)"
Write-Host "[$AgentName] non-interactive - goose will run to completion and exit." -ForegroundColor Cyan
Write-Host ""

Set-Location $AgentDir
& $GooseExe run --name $SessionName --instructions $instructionsFile
