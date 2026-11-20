# Native BRAINSTEM <-> EMIT workforce inventory smoke test.
# Run after both local services are started with matching KINDRED_INTERNAL_SERVICE_KEY.
[CmdletBinding()]
param(
    [string]$EmitBaseUrl = 'http://127.0.0.1:8000',
    [string]$BrainstemBaseUrl = 'http://127.0.0.1:8280'
)

$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($env:KINDRED_INTERNAL_SERVICE_KEY)) {
    throw 'Set KINDRED_INTERNAL_SERVICE_KEY in both service environments first.'
}
if ([string]::IsNullOrWhiteSpace($env:BRAINSTEM_AWARENESS_KEY)) {
    throw 'Set BRAINSTEM_AWARENESS_KEY in the BRAINSTEM service and this shell.'
}

$emitBase = $EmitBaseUrl.TrimEnd('/')
$brainstemBase = $BrainstemBaseUrl.TrimEnd('/')
$emitHeaders = @{ 'X-Kindred-Internal-Key' = $env:KINDRED_INTERNAL_SERVICE_KEY }
$brainstemHeaders = @{ 'X-Brainstem-Awareness-Key' = $env:BRAINSTEM_AWARENESS_KEY }

$emitHealth = Invoke-RestMethod -Method Get -Uri "$emitBase/health"
$brainstemHealth = Invoke-RestMethod -Method Get -Uri "$brainstemBase/health"
$inventory = Invoke-RestMethod -Method Get -Uri "$emitBase/runtime/workers/inventory" -Headers $emitHeaders
if ($inventory.schema_version -ne 'kindred.workforce.inventory.v1') {
    throw 'Unsupported EMIT inventory contract.'
}
$sync = Invoke-RestMethod -Method Post -Uri "$brainstemBase/awareness/sync" -Headers $brainstemHeaders
if ($sync.status -eq 'not_configured' -or $sync.status -eq 'unavailable') {
    throw "BRAINSTEM worker sync failed: $($sync.error). Configure KINDRED_EMIT_CORE_URL and KINDRED_INTERNAL_SERVICE_KEY in the BRAINSTEM process."
}
$state = Invoke-RestMethod -Method Get -Uri "$brainstemBase/awareness/workers"
$world = Invoke-RestMethod -Method Get -Uri "$brainstemBase/world"
if ($world.operational_awareness.source_of_truth -ne 'brainstem_local_state') {
    throw 'Native BRAINSTEM world does not contain the workforce projection.'
}
if ($state.summary.configured_emit_lane_definitions -ne $inventory.summary.configured_lane_definitions) {
    throw 'EMIT lane definitions do not match BRAINSTEM snapshot.'
}
[pscustomobject]@{
    emit_foundation_status     = $emitHealth.status
    brainstem_status           = $brainstemHealth.status
    configured_lane_definitions = $inventory.summary.configured_lane_definitions
    emit_online_lane_workers   = $inventory.summary.online_lane_workers
    brainstem_observed_workers = $state.summary.observed_worker_records
    brainstem_online_workers   = $state.summary.online_workers
    declared_agent_records     = $state.summary.registered_emit_agent_records
    native_world_awareness     = $true
} | Format-List
