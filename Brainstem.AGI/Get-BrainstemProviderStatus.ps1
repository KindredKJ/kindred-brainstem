#Requires -Version 7.0
[CmdletBinding()]
param([switch]$Probe,[switch]$AsJson)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
Import-Module (Join-Path $PSScriptRoot 'modules\Brainstem.IntelligenceV2.psm1') -Force
$status=@(Get-BSProviderStatus $PSScriptRoot -Probe:$Probe)
if($AsJson){$status|Select-Object Id,DisplayName,Kind,Locality,Configured,KeyPresent,Model,BaseUrl,EndpointAllowed,CloudAllowed,CircuitOpen,Reachable|ConvertTo-Json -Depth 20}
else{$status|Select-Object Id,DisplayName,Locality,Configured,KeyPresent,Model,CloudAllowed,CircuitOpen,Reachable|Format-Table -AutoSize}