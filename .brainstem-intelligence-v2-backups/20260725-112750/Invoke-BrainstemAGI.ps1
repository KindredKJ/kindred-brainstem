#Requires -Version 7.0
[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$Objective,

    [string[]]$Context = @(),

    [switch]$AsJson
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$stackRoot = $PSScriptRoot
$modulesRoot = Join-Path $stackRoot 'modules'

Import-Module (Join-Path $modulesRoot 'Brainstem.Cognition.psm1') -Force

$result = Invoke-BrainstemCognitiveCycle `
    -StackRoot $stackRoot `
    -Objective $Objective `
    -Context $Context

if ($AsJson) {
    $result | ConvertTo-Json -Depth 12
}
else {
    $result
}