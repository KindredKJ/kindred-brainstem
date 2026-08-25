Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-BrainstemDefaultPolicy {
    [CmdletBinding()]
    param()

    [pscustomobject][ordered]@{
        Schema = 'kindred.brainstem.policy.v1'
        AllowedWithoutApproval = @(
            'reason',
            'memory_read',
            'memory_write_internal',
            'benchmark',
            'integrity_read',
            'proposal_write'
        )
        RequireExplicitApproval = @(
            'network',
            'external_process',
            'filesystem_write_external',
            'self_modify',
            'credential_access',
            'external_message',
            'physical_action'
        )
        AlwaysDenied = @(
            'disable_governance',
            'erase_audit',
            'bypass_integrity',
            'forge_approval'
        )
    }
}

function New-BrainstemApprovalToken {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Scope,

        [Parameter(Mandatory)]
        [string]$ApprovedBy,

        [Parameter(Mandatory)]
        [string]$TokenStorePath,

        [ValidateRange(1, 1440)]
        [int]$ValidMinutes = 15
    )

    $tokenDirectory = Split-Path -Parent $TokenStorePath
    if (-not (Test-Path -LiteralPath $tokenDirectory)) {
        New-Item -ItemType Directory -Path $tokenDirectory -Force | Out-Null
    }

    $token = [pscustomobject][ordered]@{
        Id = [Guid]::NewGuid().ToString('N')
        Scope = $Scope
        ApprovedBy = $ApprovedBy
        CreatedAtUtc = (Get-Date).ToUniversalTime().ToString('o')
        ExpiresAtUtc = (Get-Date).ToUniversalTime().AddMinutes($ValidMinutes).ToString('o')
        Used = $false
    }

    $tokens = @()
    if (Test-Path -LiteralPath $TokenStorePath) {
        $raw = Get-Content -LiteralPath $TokenStorePath -Raw
        if (-not [string]::IsNullOrWhiteSpace($raw)) {
            $tokens = @($raw | ConvertFrom-Json)
        }
    }

    $tokens += $token
    $tokens | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $TokenStorePath -Encoding utf8NoBOM
    return $token
}

function Test-BrainstemAction {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$ActionType,

        [string]$ApprovalTokenId,

        [string]$TokenStorePath
    )

    $policy = Get-BrainstemDefaultPolicy

    if ($policy.AlwaysDenied -contains $ActionType) {
        return [pscustomobject][ordered]@{
            Allowed = $false
            Decision = 'DENY'
            Reason = 'Action is permanently prohibited by Brainstem governance.'
            ActionType = $ActionType
        }
    }

    if ($policy.AllowedWithoutApproval -contains $ActionType) {
        return [pscustomobject][ordered]@{
            Allowed = $true
            Decision = 'ALLOW'
            Reason = 'Internal governed action.'
            ActionType = $ActionType
        }
    }

    if ($policy.RequireExplicitApproval -contains $ActionType) {
        if ([string]::IsNullOrWhiteSpace($ApprovalTokenId) -or
            [string]::IsNullOrWhiteSpace($TokenStorePath) -or
            -not (Test-Path -LiteralPath $TokenStorePath)) {
            return [pscustomobject][ordered]@{
                Allowed = $false
                Decision = 'REQUIRE_APPROVAL'
                Reason = 'Explicit approval token is required.'
                ActionType = $ActionType
            }
        }

        $tokens = @(Get-Content -LiteralPath $TokenStorePath -Raw | ConvertFrom-Json)
        $token = $tokens | Where-Object {
            $_.Id -eq $ApprovalTokenId -and
            $_.Scope -eq $ActionType -and
            -not $_.Used
        } | Select-Object -First 1

        if ($null -eq $token) {
            return [pscustomobject][ordered]@{
                Allowed = $false
                Decision = 'REQUIRE_APPROVAL'
                Reason = 'Approval token is missing, used, or out of scope.'
                ActionType = $ActionType
            }
        }

        if ([datetime]$token.ExpiresAtUtc -lt (Get-Date).ToUniversalTime()) {
            return [pscustomobject][ordered]@{
                Allowed = $false
                Decision = 'REQUIRE_APPROVAL'
                Reason = 'Approval token has expired.'
                ActionType = $ActionType
            }
        }

        foreach ($candidate in $tokens) {
            if ($candidate.Id -eq $ApprovalTokenId) {
                $candidate.Used = $true
            }
        }

        $tokens | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $TokenStorePath -Encoding utf8NoBOM

        return [pscustomobject][ordered]@{
            Allowed = $true
            Decision = 'ALLOW_APPROVED'
            Reason = 'Valid single-use approval token accepted.'
            ActionType = $ActionType
        }
    }

    return [pscustomobject][ordered]@{
        Allowed = $false
        Decision = 'DENY_UNKNOWN'
        Reason = 'Unknown action types fail closed.'
        ActionType = $ActionType
    }
}

Export-ModuleMember -Function @(
    'Get-BrainstemDefaultPolicy',
    'New-BrainstemApprovalToken',
    'Test-BrainstemAction'
)