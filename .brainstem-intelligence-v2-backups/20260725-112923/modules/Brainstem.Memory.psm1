Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Initialize-BrainstemMemory {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$StateRoot
    )

    if (-not (Test-Path -LiteralPath $StateRoot)) {
        New-Item -ItemType Directory -Path $StateRoot -Force | Out-Null
    }

    $memoryPath = Join-Path $StateRoot 'memory.jsonl'
    $auditPath = Join-Path $StateRoot 'memory-audit.jsonl'

    foreach ($path in @($memoryPath, $auditPath)) {
        if (-not (Test-Path -LiteralPath $path)) {
            New-Item -ItemType File -Path $path -Force | Out-Null
        }
    }

    [pscustomobject][ordered]@{
        StateRoot = $StateRoot
        MemoryPath = $memoryPath
        AuditPath = $auditPath
    }
}

function Add-BrainstemMemory {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$StateRoot,

        [Parameter(Mandatory)]
        [ValidateSet('episodic', 'semantic', 'procedural', 'decision', 'benchmark')]
        [string]$Type,

        [Parameter(Mandatory)]
        [string]$Content,

        [string[]]$Tags = @(),

        [ValidateRange(0.0, 1.0)]
        [double]$Confidence = 1.0,

        [string]$Source = 'brainstem'
    )

    $paths = Initialize-BrainstemMemory -StateRoot $StateRoot

    $record = [pscustomobject][ordered]@{
        Id = [Guid]::NewGuid().ToString('N')
        TimestampUtc = (Get-Date).ToUniversalTime().ToString('o')
        Type = $Type
        Content = $Content
        Tags = @($Tags)
        Confidence = $Confidence
        Source = $Source
    }

    $line = $record | ConvertTo-Json -Compress -Depth 6
    Add-Content -LiteralPath $paths.MemoryPath -Value $line -Encoding utf8NoBOM

    $audit = [pscustomobject][ordered]@{
        TimestampUtc = (Get-Date).ToUniversalTime().ToString('o')
        Operation = 'ADD'
        RecordId = $record.Id
        Type = $Type
        Source = $Source
    }
    Add-Content -LiteralPath $paths.AuditPath -Value ($audit | ConvertTo-Json -Compress) -Encoding utf8NoBOM

    return $record
}

function Get-BrainstemMemoryRecords {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$StateRoot
    )

    $paths = Initialize-BrainstemMemory -StateRoot $StateRoot
    $records = [System.Collections.Generic.List[object]]::new()

    foreach ($line in Get-Content -LiteralPath $paths.MemoryPath -ErrorAction Stop) {
        if ([string]::IsNullOrWhiteSpace($line)) {
            continue
        }

        try {
            $records.Add(($line | ConvertFrom-Json))
        }
        catch {
            # Corrupt lines are skipped but preserved for forensic review.
        }
    }

    return @($records)
}

function Search-BrainstemMemory {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$StateRoot,

        [Parameter(Mandatory)]
        [string]$Query,

        [ValidateRange(1, 100)]
        [int]$Top = 5
    )

    $tokens = @(
        $Query.ToLowerInvariant() -split '[^a-z0-9]+' |
        Where-Object { $_.Length -ge 2 } |
        Select-Object -Unique
    )

    $scored = foreach ($record in Get-BrainstemMemoryRecords -StateRoot $StateRoot) {
        $haystack = (
            [string]$record.Content + ' ' +
            [string]$record.Type + ' ' +
            (@($record.Tags) -join ' ')
        ).ToLowerInvariant()

        [double]$score = 0.0
        foreach ($token in $tokens) {
            if ($haystack.Contains($token)) {
                $score += 2.0
            }
        }

        if ($record.Type -eq 'semantic') {
            $score += 0.25
        }

        $ageHours = [Math]::Max(
            0.0,
            ((Get-Date).ToUniversalTime() - [datetime]$record.TimestampUtc).TotalHours
        )
        $score += 1.0 / (1.0 + ($ageHours / 24.0))
        $score *= [double]$record.Confidence

        if ($score -gt 0.0) {
            [pscustomobject][ordered]@{
                Score = [Math]::Round($score, 4)
                Record = $record
            }
        }
    }

    return @(
        $scored |
        Sort-Object Score -Descending |
        Select-Object -First $Top
    )
}

function Get-BrainstemMemoryStats {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$StateRoot
    )

    $records = @(Get-BrainstemMemoryRecords -StateRoot $StateRoot)
    $byType = @{}

    foreach ($record in $records) {
        $key = [string]$record.Type
        if (-not $byType.ContainsKey($key)) {
            $byType[$key] = 0
        }
        $byType[$key]++
    }

    [pscustomobject][ordered]@{
        Total = $records.Count
        ByType = $byType
        StateRoot = $StateRoot
    }
}

Export-ModuleMember -Function @(
    'Initialize-BrainstemMemory',
    'Add-BrainstemMemory',
    'Get-BrainstemMemoryRecords',
    'Search-BrainstemMemory',
    'Get-BrainstemMemoryStats'
)