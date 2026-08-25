#Requires -Version 7.0
[CmdletBinding(DefaultParameterSetName='Start')]
param(
  [Parameter(Mandatory,ParameterSetName='Start')][string]$Objective,
  [Parameter(Mandatory,ParameterSetName='Resume')][string]$TaskId,
  [int]$MaximumSteps=20,
  [int]$MaximumMinutes=60,
  [switch]$AsJson
)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
Import-Module (Join-Path $PSScriptRoot 'modules\Brainstem.IntelligenceV2.psm1') -Force
if($PSCmdlet.ParameterSetName -eq 'Resume'){$result=Resume-BSLongTask $PSScriptRoot $TaskId}
else{$result=Start-BSLongTask $PSScriptRoot $Objective $MaximumSteps $MaximumMinutes}
if($AsJson){$result|ConvertTo-Json -Depth 50}else{$result}