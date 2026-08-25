Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Import-Module (Join-Path $PSScriptRoot 'Brainstem.Governance.psm1') -Force
Import-Module (Join-Path $PSScriptRoot 'Brainstem.Memory.psm1') -Force

function New-BrainstemPlan {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Objective,

        [string[]]$Context = @()
    )

    $steps = [System.Collections.Generic.List[object]]::new()
    $steps.Add([pscustomobject][ordered]@{
        Index = 1
        Phase = 'UNDERSTAND'
        Instruction = 'Parse the objective, constraints, and success condition.'
    })
    $steps.Add([pscustomobject][ordered]@{
        Index = 2
        Phase = 'RECALL'
        Instruction = 'Retrieve relevant durable memory and prior decisions.'
    })
    $steps.Add([pscustomobject][ordered]@{
        Index = 3
        Phase = 'REASON'
        Instruction = 'Construct a candidate solution using the objective and retrieved context.'
    })
    $steps.Add([pscustomobject][ordered]@{
        Index = 4
        Phase = 'CRITIQUE'
        Instruction = 'Check completeness, contradictions, policy compliance, and uncertainty.'
    })
    $steps.Add([pscustomobject][ordered]@{
        Index = 5
        Phase = 'COMMIT'
        Instruction = 'Return the best supported result and store reusable learning.'
    })

    [pscustomobject][ordered]@{
        Objective = $Objective
        Context = @($Context)
        Steps = @($steps)
        CreatedAtUtc = (Get-Date).ToUniversalTime().ToString('o')
    }
}

function New-BrainstemImprovementProposal {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$StackRoot,

        [Parameter(Mandatory)]
        [string]$Title,

        [Parameter(Mandatory)]
        [string]$Rationale,

        [Parameter(Mandatory)]
        [string[]]$ProposedChanges
    )

    $proposalDecision = Test-BrainstemAction -ActionType 'proposal_write'
    if (-not $proposalDecision.Allowed) {
        throw "Proposal creation blocked: $($proposalDecision.Reason)"
    }

    $proposalRoot = Join-Path $StackRoot 'state\improvement-proposals'
    if (-not (Test-Path -LiteralPath $proposalRoot)) {
        New-Item -ItemType Directory -Path $proposalRoot -Force | Out-Null
    }

    $proposal = [pscustomobject][ordered]@{
        Schema = 'kindred.brainstem.improvement-proposal.v1'
        Id = [Guid]::NewGuid().ToString('N')
        Title = $Title
        Rationale = $Rationale
        ProposedChanges = @($ProposedChanges)
        Status = 'AWAITING_FOUNDER_APPROVAL'
        CreatedAtUtc = (Get-Date).ToUniversalTime().ToString('o')
        MayAutoApply = $false
    }

    $path = Join-Path $proposalRoot "$($proposal.Id).json"
    $proposal | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $path -Encoding utf8NoBOM

    [pscustomobject][ordered]@{
        Proposal = $proposal
        Path = $path
    }
}

function Invoke-BrainstemCognitiveCycle {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$StackRoot,

        [Parameter(Mandatory)]
        [string]$Objective,

        [string[]]$Context = @(),

        [scriptblock]$Reasoner
    )

    $cycleId = [Guid]::NewGuid().ToString('N')
    $stateRoot = Join-Path $StackRoot 'state'

    $governance = Test-BrainstemAction -ActionType 'reason'
    if (-not $governance.Allowed) {
        throw "Cognitive cycle blocked: $($governance.Reason)"
    }

    $plan = New-BrainstemPlan -Objective $Objective -Context $Context
    $memoryHits = @(Search-BrainstemMemory -StateRoot $stateRoot -Query $Objective -Top 5)

    if ($null -ne $Reasoner) {
        $candidate = & $Reasoner ([pscustomobject][ordered]@{
            Objective = $Objective
            Context = @($Context)
            Memory = @($memoryHits)
            Plan = $plan
        })
    }
    else {
        $candidate = [pscustomobject][ordered]@{
            Summary = 'Objective processed through the governed Brainstem cognitive cycle.'
            Objective = $Objective
            RecalledMemoryCount = $memoryHits.Count
            NextRequiredCapability = 'Connect an approved model adapter for open-domain reasoning.'
        }
    }

    $critiqueFindings = [System.Collections.Generic.List[string]]::new()
    if ([string]::IsNullOrWhiteSpace($Objective)) {
        $critiqueFindings.Add('Objective is empty.')
    }
    if ($plan.Steps.Count -lt 4) {
        $critiqueFindings.Add('Plan is under-specified.')
    }
    if ($null -eq $candidate) {
        $critiqueFindings.Add('Reasoner returned no candidate result.')
    }

    $status = if ($critiqueFindings.Count -eq 0) { 'COMPLETED' } else { 'NEEDS_REVIEW' }
    $confidence = if ($status -eq 'COMPLETED') { 0.80 } else { 0.35 }

    $critique = [pscustomobject][ordered]@{
        Status = $status
        Findings = @($critiqueFindings)
        GovernanceDecision = $governance.Decision
        Confidence = $confidence
    }

    Add-BrainstemMemory `
        -StateRoot $stateRoot `
        -Type 'episodic' `
        -Content "Objective: $Objective | Status: $status" `
        -Tags @('cognitive-cycle', $cycleId) `
        -Confidence $confidence `
        -Source 'Brainstem.Cognition' | Out-Null

    $result = [pscustomobject][ordered]@{
        Schema = 'kindred.brainstem.cycle.v1'
        CycleId = $cycleId
        StartedAtUtc = (Get-Date).ToUniversalTime().ToString('o')
        Objective = $Objective
        Plan = $plan
        RecalledMemory = @($memoryHits)
        Candidate = $candidate
        Critique = $critique
        Status = $status
        Confidence = $confidence
    }

    return $result
}

Export-ModuleMember -Function @(
    'New-BrainstemPlan',
    'New-BrainstemImprovementProposal',
    'Invoke-BrainstemCognitiveCycle'
)