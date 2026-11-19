#Requires -Version 7.0
# Isolated Windows 11 / PowerShell 7 two-service live integration and failure test.
param([string]$Python='python',[int]$EmitPort=18001,[int]$BrainPort=18281)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$original=@{}
$envKeys=@('KINDRED_INTERNAL_SERVICE_KEY','BRAINSTEM_AWARENESS_KEY','KINDRED_EMIT_CORE_URL','KINDRED_SQLITE_PATH','KINDRED_STATE_DB','KINDRED_CLOUD_USE_LOCAL_STORE')
foreach($k in $envKeys){$original[$k]=[Environment]::GetEnvironmentVariable($k,'Process')}
$root=Join-Path ([IO.Path]::GetTempPath()) ('Kindred-Workforce-E2E-'+[guid]::NewGuid().ToString('N'))
$er=Join-Path $root 'EMIT'; $br=Join-Path $root 'BRAINSTEM'
$ep=$null; $bp=$null
function VerifyExit([string]$name){if($LASTEXITCODE -ne 0){throw "$name exit code $LASTEXITCODE"}}
function Resolve-CompatiblePython([string]$preferred) {
  $probe = 'import sys; print(sys.executable if sys.version_info >= (3,12) else "")'
  foreach($candidate in @($preferred,'python3.13','python3.12','python3.14')) {
    if([string]::IsNullOrWhiteSpace($candidate)) { continue }
    if(-not (Get-Command $candidate -ErrorAction SilentlyContinue)) { continue }
    try {
      $found = & $candidate -c $probe 2>$null
      $exe = [string]($found | Select-Object -Last 1)
      if($LASTEXITCODE -eq 0 -and $exe -and (Test-Path -LiteralPath $exe.Trim() -PathType Leaf)) {
        return $exe.Trim()
      }
    } catch { }
  }
  if(Get-Command py -ErrorAction SilentlyContinue) {
    foreach($version in @('3.12','3.13','3.14')) {
      try {
        $found = & py "-$version" -c $probe 2>$null
        $exe = [string]($found | Select-Object -Last 1)
        if($LASTEXITCODE -eq 0 -and $exe -and (Test-Path -LiteralPath $exe.Trim() -PathType Leaf)) {
          return $exe.Trim()
        }
      } catch { }
    }
  }
  throw 'Python 3.12+ not found. Install alongside existing Python: winget install --id Python.Python.3.12 --exact --source winget --accept-package-agreements --accept-source-agreements; then retry. Run py -0p to inspect installed interpreters.'
}
function WaitUrl([string]$url,[Diagnostics.Process]$proc,[string]$err){
  $limit=(Get-Date).AddSeconds(90)
  while((Get-Date) -lt $limit){
    if($proc.HasExited){throw "Service exited: $((Get-Content $err -Tail 30) -join [Environment]::NewLine)"}
    try{return Invoke-RestMethod -Uri $url -TimeoutSec 2}catch{Start-Sleep -Milliseconds 750}
  }
  throw "Service startup timeout: $url. Log: $err"
}
function CheckFree([int]$port){
  if($port -lt 1024 -or $port -gt 65535){throw 'Ports must be between 1024 and 65535'}
  $c=[Net.Sockets.TcpClient]::new()
  try{$a=$c.BeginConnect('127.0.0.1',$port,$null,$null);if($a.AsyncWaitHandle.WaitOne(200) -and $c.Connected){throw "Port $port in use; no other service will be stopped"}}finally{$c.Dispose()}
}
try{
  if($EmitPort -eq $BrainPort){throw 'Port numbers must differ'}
  CheckFree $EmitPort; CheckFree $BrainPort
  New-Item -ItemType Directory -Path $root -Force | Out-Null
  $env:KINDRED_SQLITE_PATH=Join-Path $root 'emit.db'
  $env:KINDRED_STATE_DB=Join-Path $root 'brainstem.db'
  $env:KINDRED_CLOUD_USE_LOCAL_STORE='1'
  & git --version | Out-Null; VerifyExit 'git'
  $Python=Resolve-CompatiblePython $Python
  Write-Host "Using compatible interpreter: $Python"
  & $Python -c "import sys; print('Python',sys.version.split()[0])"; VerifyExit 'Python verification'
  & git clone --depth 1 -b feature/native-workforce-inventory-20261118 https://github.com/KindredKJ/KINDRED_EMIT_CORE.git $er
  VerifyExit 'Private EMIT clone; authenticate Git first'
  & git clone --depth 1 -b feature/native-organizational-awareness-20261118 https://github.com/KindredKJ/kindred-brainstem.git $br
  VerifyExit 'BRAINSTEM clone'
  & $Python -m venv (Join-Path $er '.venv'); VerifyExit 'EMIT venv'
  & $Python -m venv (Join-Path $br '.venv'); VerifyExit 'BRAINSTEM venv'
  $ePython=Join-Path $er '.venv\Scripts\python.exe'
  $bPython=Join-Path $br '.venv\Scripts\python.exe'
  Push-Location $er
  try{
    & $ePython -m pip install -r requirements.txt; VerifyExit 'EMIT install'
    & $ePython -m pip check; VerifyExit 'EMIT pip check'
    & $ePython -m pytest -q cloud/tests/test_worker_inventory.py; VerifyExit 'EMIT tests'
  }finally{Pop-Location}
  Push-Location $br
  try{
    & $bPython -m pip install -e '.[dev]'; VerifyExit 'BRAINSTEM install'
    & $bPython -m pip check; VerifyExit 'BRAINSTEM pip check'
    & $bPython -m pytest -q tests/test_workforce_awareness.py; VerifyExit 'BRAINSTEM tests'
  }finally{Pop-Location}
  $bytes=[byte[]]::new(32);[Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
  $env:KINDRED_INTERNAL_SERVICE_KEY=[Convert]::ToHexString($bytes)
  [Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
  $env:BRAINSTEM_AWARENESS_KEY=[Convert]::ToHexString($bytes)
  $env:KINDRED_EMIT_CORE_URL="http://127.0.0.1:$EmitPort"
  $env:KINDRED_SQLITE_PATH=Join-Path $root 'emit.db'
  $env:KINDRED_STATE_DB=Join-Path $root 'brainstem.db'
  $env:KINDRED_CLOUD_USE_LOCAL_STORE='1'
  $eErr=Join-Path $root 'emit.err.log'; $bErr=Join-Path $root 'brainstem.err.log'
  $ep=Start-Process -FilePath $ePython -WorkingDirectory $er -ArgumentList @('-m','uvicorn','cloud.api.main:app','--host','127.0.0.1','--port',"$EmitPort") -PassThru -RedirectStandardOutput (Join-Path $root 'emit.out.log') -RedirectStandardError $eErr
  $eh=WaitUrl "http://127.0.0.1:$EmitPort/health" $ep $eErr
  if(-not $eh.foundation.foundation_ready){throw "EMIT foundation not ready: $($eh|ConvertTo-Json -Depth 8)"}
  $bp=Start-Process -FilePath $bPython -WorkingDirectory $br -ArgumentList @('-m','uvicorn','brainstem.runtime.app:app','--host','127.0.0.1','--port',"$BrainPort") -PassThru -RedirectStandardOutput (Join-Path $root 'brainstem.out.log') -RedirectStandardError $bErr
  $null=WaitUrl "http://127.0.0.1:$BrainPort/health" $bp $bErr
  $eBase="http://127.0.0.1:$EmitPort";$bBase="http://127.0.0.1:$BrainPort"
  try{Invoke-WebRequest "$eBase/runtime/workers/inventory" -TimeoutSec 3 | Out-Null; throw 'EMIT accepted unauthenticated inventory request'}
  catch{if(-not $_.Exception.Response -or [int]$_.Exception.Response.StatusCode -ne 401){throw}}
  $ehdr=@{'X-Kindred-Internal-Key'=$env:KINDRED_INTERNAL_SERVICE_KEY}
  $bhdr=@{'X-Brainstem-Awareness-Key'=$env:BRAINSTEM_AWARENESS_KEY}
  $i=Invoke-RestMethod "$eBase/runtime/workers/inventory" -Headers $ehdr
  if($i.schema_version -ne 'kindred.workforce.inventory.v1' -or $i.summary.configured_lane_definitions -ne 14 -or $i.summary.online_lane_workers -lt 1){throw 'EMIT live worker contract failed'}
  $s=Invoke-RestMethod "$bBase/awareness/sync" -Method Post -Headers $bhdr
  $w=Invoke-RestMethod "$bBase/awareness/workers"
  $world=Invoke-RestMethod "$bBase/world"
  if($s.status -ne 'observations_available' -or $w.summary.online_workers -ne $i.summary.online_lane_workers){throw 'BRAINSTEM live worker counts failed'}
  if($world.operational_awareness.source_of_truth -ne 'brainstem_local_state'){throw 'BRAINSTEM cognition world not connected'}
  if($w.summary.registered_emit_agent_records -ne $i.summary.registered_agent_records){throw 'Agent registration distinction failed'}
  Write-Host 'Live sync passed. Testing worker loss; waiting 65 seconds for observation TTL.'
  Stop-Process -Id $ep.Id -Force; $null=$ep.WaitForExit(10000)
  Start-Sleep -Seconds 65
  $stale=Invoke-RestMethod "$bBase/awareness/workers"
  if($stale.summary.online_workers -ne 0){throw 'Stale workers incorrectly online'}
  $stillFresh=@($stale.workers | Where-Object {$_.source -eq 'kindred_emit_core' -and $_.status -ne 'stale'})
  if($stillFresh.Count -gt 0){throw 'Worker loss was not marked stale'}
  [pscustomobject]@{result='PASS';observed_lane_workers=$i.summary.online_lane_workers;registered_agent_records=$i.summary.registered_agent_records;online_after_loss=$stale.summary.online_workers;persisted_records=$stale.summary.observed_worker_records;logs=$root} | Format-List
}finally{
  foreach($p in @($ep,$bp)){if($null -ne $p){try{if(-not $p.HasExited){Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue}}catch{};$p.Dispose()}}
  foreach($k in $envKeys){[Environment]::SetEnvironmentVariable($k,$original[$k],'Process')}
  Write-Host "Workspace and diagnostic logs retained at: $root"
}
