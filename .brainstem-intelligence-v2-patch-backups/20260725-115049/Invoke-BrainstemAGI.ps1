#Requires -Version 7.0
[CmdletBinding()]
param(
  [Parameter(Mandatory)][string]$Objective,
  [string[]]$Context=@(),
  [ValidateSet('LocalFirst','CloudFirst','Balanced','PrivacyOnly')][string]$RoutingMode,
  [int]$MaximumProviders=3,
  [switch]$AsJson
)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
Import-Module (Join-Path $PSScriptRoot 'modules\Brainstem.IntelligenceV2.psm1') -Force
$result=Invoke-BSArchitecturalAudit $PSScriptRoot $Objective $Context $RoutingMode $MaximumProviders
if($AsJson){$result|ConvertTo-Json -Depth 50}else{$result}