# opencode.ps1 - non-interactive opencode run against build-prompt.md inside opencode/
# Same approach as goose.ps1: spec inlined, agent runs from a single arg, no TUI paste.
# Caveat: opencode is also a tool-call agent; qwen3-coder:30b will be hit-or-miss
# on tool-call reliability. aider is the more forgiving path for local LLMs.

$ErrorActionPreference = 'Stop'

$Root        = 'P:\Documents\GIT\RedditScraper'
$Spec        = Join-Path $Root 'build-prompt.md'
$AgentDir    = Join-Path $Root 'opencode'
$AgentName   = 'opencode'
$OpencodeExe = 'C:\Users\Quadstronaut\scoop\apps\nodejs\current\bin\opencode.cmd'

if (-not (Test-Path $Spec))        { throw "Spec not found: $Spec" }
if (-not (Test-Path $AgentDir))    { throw "Agent dir not found: $AgentDir" }
if (-not (Test-Path $OpencodeExe)) { throw "opencode.cmd not found: $OpencodeExe" }

try {
    $r = Invoke-WebRequest -Uri 'http://localhost:11434/api/tags' -UseBasicParsing -TimeoutSec 3
    if ($r.StatusCode -ne 200) { throw "ollama returned $($r.StatusCode)" }
} catch {
    throw "Ollama not reachable at http://localhost:11434 - start it before running this script. ($_)"
}

$specContent = Get-Content -Raw -LiteralPath $Spec
$prompt = @"
You are working in the current directory: $AgentDir
The git repo root is: $Root
Filesystem MCP is rooted at P:\Documents\GIT - use absolute paths under that root for any file operation.

Execute the spec below inside the current working directory ($AgentDir). Build every file the spec lists. After each major file (pyproject.toml, schema.py, fetch.py, summarize.py, render.py, cli.py, mcp_server.py) commit via the shell with message "$($AgentName): <file>". Stop after the acceptance check passes.

Do NOT call any tool to read the spec - it is inlined below in full.

===== BEGIN build-prompt.md =====
$specContent
===== END build-prompt.md =====
"@

Write-Host ""
Write-Host "[$AgentName] cwd    : $AgentDir"
Write-Host "[$AgentName] model  : ollama/qwen3-coder:30b (from ~/.config/opencode/opencode.json)"
Write-Host "[$AgentName] non-interactive - opencode will run to completion and exit." -ForegroundColor Cyan
Write-Host ""

Set-Location $AgentDir
& $OpencodeExe run $prompt
