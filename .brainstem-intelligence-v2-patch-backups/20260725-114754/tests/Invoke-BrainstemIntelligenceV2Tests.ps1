#Requires -Version 7.0
[CmdletBinding()]
param([bool]$LiveProviderTests=$true,[switch]$RequireLiveProvider)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$stackRoot=Split-Path -Parent $PSScriptRoot
Import-Module (Join-Path $stackRoot 'modules\Brainstem.IntelligenceV2.psm1') -Force
$run=Invoke-BSV2Tests $stackRoot $LiveProviderTests -RequireLiveProvider:$RequireLiveProvider
Write-Host "`nBRAINSTEM INTELLIGENCE V2 TEST" -ForegroundColor Cyan
foreach($test in $run.Report.results){
  $color=if($test.Status -eq 'PASS'){'Green'}elseif($test.Status -eq 'FAIL'){'Red'}else{'Yellow'}
  Write-Host "[$($test.Status)] $($test.Name): $($test.Evidence)" -ForegroundColor $color
}
Write-Host "Report: $($run.ReportPath)"
if(-not $run.Report.passed){throw 'Brainstem Intelligence v2 tests failed.'}
Write-Host '[PASS] Brainstem Intelligence Runtime v2 validated.' -ForegroundColor Green
$run