#Requires -Version 7.0
[CmdletBinding()]
param(
    [ValidateRange(0, 100)]
    [int]$PassingScore = 85
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$stackRoot = Split-Path -Parent $PSScriptRoot
$modulesRoot = Join-Path $stackRoot 'modules'
$integrityRoot = Join-Path $stackRoot 'integrity'

function Get-HmacSha256Hex {
    param(
        [byte[]]$Key,
        [byte[]]$Data
    )

    $hmac = [System.Security.Cryptography.HMACSHA256]::new($Key)
    try {
        [Convert]::ToHexString($hmac.ComputeHash($Data)).ToLowerInvariant()
    }
    finally {
        $hmac.Dispose()
    }
}

function Assert-IntegrityLock {
    $manifestPath = Join-Path $integrityRoot 'manifest.json'
    $signaturePath = Join-Path $integrityRoot 'manifest.hmac'
    $keyPath = Join-Path $integrityRoot 'lock.key'
    $statePath = Join-Path $integrityRoot 'LOCKED'

    foreach ($required in @($manifestPath, $signaturePath, $keyPath, $statePath)) {
        if (-not (Test-Path -LiteralPath $required)) {
            throw "Integrity artifact missing: $required"
        }
    }

    $manifestBytes = [System.IO.File]::ReadAllBytes($manifestPath)
    $key = [System.IO.File]::ReadAllBytes($keyPath)
    $expectedSignature = ([System.IO.File]::ReadAllText($signaturePath)).Trim().ToLowerInvariant()
    $actualSignature = Get-HmacSha256Hex -Key $key -Data $manifestBytes

    if ($actualSignature -ne $expectedSignature) {
        throw 'Integrity manifest signature mismatch.'
    }

    $manifest = [System.Text.Encoding]::UTF8.GetString($manifestBytes) | ConvertFrom-Json

    foreach ($entry in $manifest.files) {
        $path = Join-Path $stackRoot ([string]$entry.path)
        if (-not (Test-Path -LiteralPath $path)) {
            throw "Locked file missing: $($entry.path)"
        }

        $actualHash = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actualHash -ne ([string]$entry.sha256).ToLowerInvariant()) {
            throw "Locked file changed: $($entry.path)"
        }
    }

    return $true
}

Write-Host "`nBRAINSTEM AGI FOUNDATION TEST" -ForegroundColor Cyan
Write-Host "Stack: $stackRoot"

Assert-IntegrityLock | Out-Null
Write-Host '[PASS] Cryptographic integrity lock verified.' -ForegroundColor Green

Import-Module (Join-Path $modulesRoot 'Brainstem.Benchmarks.psm1') -Force

$run = Invoke-BrainstemBenchmarkSuite `
    -StackRoot $stackRoot `
    -PassingScore $PassingScore

foreach ($category in $run.Report.CategoryScores) {
    $color = if ($category.Passed) { 'Green' } else { 'Red' }
    Write-Host ("[{0}] {1}: {2}%" -f (
        $(if ($category.Passed) { 'PASS' } else { 'FAIL' }),
        $category.Category,
        $category.Score
    )) -ForegroundColor $color
}

Write-Host "`nOverall score: $($run.Report.Score)%"
Write-Host "Report: $($run.ReportPath)"

if (-not $run.Report.Passed) {
    Write-Host '[FAIL] Brainstem AGI foundation did not meet the required threshold.' -ForegroundColor Red
    throw 'Brainstem AGI foundation did not meet the required threshold.'
}

Write-Host '[PASS] Brainstem AGI foundation is locked and validated.' -ForegroundColor Green
return $run