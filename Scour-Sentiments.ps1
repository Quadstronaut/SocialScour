<#
.SYNOPSIS
    Interactive launcher for SocialScour. Walks you through running sentiment
    scans across Reddit / Google Trends / Hacker News / IndieHackers and opens
    the resulting summary.

.DESCRIPTION
    Wraps the `scour` CLI (from this repo's pyproject.toml) with prompts so
    you don't have to remember flag names. Pre-flight checks Ollama and the
    `scour` command, then presents a menu:

        1. Sentiment scan on a topic        (scour ask)
        2. Discover trending topics         (scour discover)
        3. Show timeline for a topic slug   (scour timeline)
        4. List recent runs                 (scour list)
        5. Open the latest summary
        Q. Quit

.NOTES
    Run from anywhere -- the script cd's into its own directory before invoking
    scour so relative `data/` and `cache/` paths resolve correctly.
#>

[CmdletBinding()]
param(
    [string]$DataRoot = "data",
    [string]$Model    = "qwen3-coder:30b"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepoRoot

# ---------- pretty helpers ----------
function Write-Heading($text) {
    Write-Host ""
    Write-Host ("=" * 60) -ForegroundColor DarkCyan
    Write-Host "  $text" -ForegroundColor Cyan
    Write-Host ("=" * 60) -ForegroundColor DarkCyan
}
function Write-Step($text)   { Write-Host "  > $text" -ForegroundColor Yellow }
function Write-Ok($text)     { Write-Host "  [ok]  $text" -ForegroundColor Green }
function Write-Bad($text)    { Write-Host "  [!!]  $text" -ForegroundColor Red }
function Read-Default($prompt, $default) {
    $v = Read-Host "  $prompt [$default]"
    if ([string]::IsNullOrWhiteSpace($v)) { return $default } else { return $v }
}

# ---------- pre-flight ----------
function Test-Prereqs {
    Write-Heading "Pre-flight checks"

    $scour = Get-Command scour -ErrorAction SilentlyContinue
    if (-not $scour) {
        Write-Bad "'scour' command not found on PATH."
        Write-Host "       Install it from this repo with:" -ForegroundColor DarkGray
        Write-Host "         pip install -e .[dev]" -ForegroundColor DarkGray
        return $false
    }
    Write-Ok "scour CLI found at $($scour.Source)"

    try {
        $ping = Invoke-WebRequest -Uri "http://localhost:11434/api/tags" -UseBasicParsing -TimeoutSec 2
        if ($ping.StatusCode -eq 200) {
            Write-Ok "Ollama is reachable on :11434"
        }
    } catch {
        Write-Bad "Ollama not reachable on :11434 -- start it with 'ollama serve' in another terminal."
        Write-Host "       (You can still continue if you only plan to use --summarizer claude.)" -ForegroundColor DarkGray
        $cont = Read-Host "  Continue anyway? [y/N]"
        if ($cont -notmatch '^[Yy]') { return $false }
    }

    if (-not (Test-Path $DataRoot)) {
        New-Item -ItemType Directory -Path $DataRoot | Out-Null
        Write-Ok "Created $DataRoot/"
    }
    return $true
}

# ---------- source picker ----------
function Read-Sources {
    Write-Host ""
    Write-Host "  Pick sources (comma-separated numbers, or Enter for all):" -ForegroundColor Yellow
    Write-Host "    1) reddit"
    Write-Host "    2) trends   (Google Trends)"
    Write-Host "    3) hn       (Hacker News)"
    Write-Host "    4) ih       (IndieHackers)"
    $raw = Read-Host "  Choice"
    if ([string]::IsNullOrWhiteSpace($raw)) { return $null }

    $map = @{ "1" = "reddit"; "2" = "trends"; "3" = "hn"; "4" = "ih" }
    $picked = foreach ($n in $raw.Split(",")) {
        $key = $n.Trim()
        if ($map.ContainsKey($key)) { $map[$key] }
    }
    if (-not $picked) { return $null }
    return ($picked -join ",")
}

function Read-Window {
    Write-Host ""
    Write-Host "  Time window (days):" -ForegroundColor Yellow
    Write-Host "    1) 7   (this week)"
    Write-Host "    2) 14  (this fortnight)"
    Write-Host "    3) 30  (this month)            [default]"
    Write-Host "    4) 90  (this quarter)"
    Write-Host "    5) custom"
    $c = Read-Host "  Choice"
    switch ($c) {
        "1" { return 7 }
        "2" { return 14 }
        "4" { return 90 }
        "5" {
            $n = Read-Host "  Enter days"
            if ($n -as [int]) { return [int]$n } else { return 30 }
        }
        default { return 30 }
    }
}

function Read-Summarizer {
    Write-Host ""
    Write-Host "  Summarizer:" -ForegroundColor Yellow
    Write-Host "    1) ollama   (local, free)              [default]"
    Write-Host "    2) claude   (uses Claude Code, costs $)"
    $c = Read-Host "  Choice"
    if ($c -eq "2") { return "claude" } else { return "ollama" }
}

# ---------- actions ----------
function Invoke-AskFlow {
    Write-Heading "Sentiment scan on a topic"
    $topic = Read-Host "  Topic (e.g. 'local-first sync engines')"
    if ([string]::IsNullOrWhiteSpace($topic)) { Write-Bad "No topic -- aborting."; return }

    $window     = Read-Window
    $sources    = Read-Sources
    $summarizer = Read-Summarizer

    $args = @("ask", $topic, "--window-days", $window, "--summarizer", $summarizer,
              "--model", $Model, "--out", $DataRoot)
    if ($sources) { $args += @("--sources", $sources) }

    Write-Host ""
    Write-Step ("scour " + ($args -join " "))
    Write-Host ""
    & scour @args
    if ($LASTEXITCODE -eq 0) {
        Open-LatestSummary -Prompt
    } else {
        Write-Bad "scour exited with code $LASTEXITCODE"
    }
}

function Invoke-DiscoverFlow {
    Write-Heading "Discover trending topics"
    $window  = Read-Window
    $topN    = Read-Default "How many topics to dig into" 5
    $sources = Read-Sources

    $args = @("discover", "--window-days", $window, "--top-n", $topN,
              "--model", $Model, "--out", $DataRoot)
    if ($sources) { $args += @("--sources", $sources) }

    Write-Host ""
    Write-Step ("scour " + ($args -join " "))
    Write-Host ""
    & scour @args
    if ($LASTEXITCODE -eq 0) { Open-LatestSummary -Prompt }
}

function Invoke-TimelineFlow {
    Write-Heading "Topic timeline"
    $topicsDir = Join-Path $DataRoot "topics"
    if (Test-Path $topicsDir) {
        Write-Host "  Known slugs:" -ForegroundColor DarkGray
        Get-ChildItem -Directory $topicsDir | ForEach-Object {
            Write-Host "    - $($_.Name)" -ForegroundColor DarkGray
        }
    }
    $slug = Read-Host "  Slug"
    if ([string]::IsNullOrWhiteSpace($slug)) { return }
    & scour timeline $slug --data-root $DataRoot
}

function Invoke-ListFlow {
    Write-Heading "Recent runs"
    $limit = Read-Default "How many to show" 10
    & scour list --data-root $DataRoot --limit $limit
}

function Open-LatestSummary {
    param([switch]$Prompt)
    $runsDir = Join-Path $DataRoot "runs"
    if (-not (Test-Path $runsDir)) { Write-Bad "No runs found yet."; return }
    $latest = Get-ChildItem -Directory $runsDir | Sort-Object Name -Descending | Select-Object -First 1
    if (-not $latest) { Write-Bad "No runs found yet."; return }
    $summary = Join-Path $latest.FullName "summary\summary.md"
    if (-not (Test-Path $summary)) { Write-Bad "Latest run has no summary.md ($summary)"; return }

    if ($Prompt) {
        $ans = Read-Host "  Open $summary now? [Y/n]"
        if ($ans -match '^[Nn]') { return }
    }
    Write-Ok "Opening $summary"
    Start-Process $summary
}

# ---------- menu loop ----------
if (-not (Test-Prereqs)) { exit 1 }

while ($true) {
    Write-Heading "SocialScour -- what do you want to do?"
    Write-Host "    1) Sentiment scan on a topic       (scour ask)"
    Write-Host "    2) Discover trending topics        (scour discover)"
    Write-Host "    3) Show timeline for a topic slug  (scour timeline)"
    Write-Host "    4) List recent runs                (scour list)"
    Write-Host "    5) Open the latest summary"
    Write-Host "    Q) Quit"
    $choice = Read-Host "  Choice"
    switch ($choice.ToLower()) {
        "1" { Invoke-AskFlow }
        "2" { Invoke-DiscoverFlow }
        "3" { Invoke-TimelineFlow }
        "4" { Invoke-ListFlow }
        "5" { Open-LatestSummary }
        "q" { break }
        default { Write-Bad "Pick 1-5 or Q." }
    }
}

Write-Host ""
Write-Host "  bye." -ForegroundColor DarkCyan
