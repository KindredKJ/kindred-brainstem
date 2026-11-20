#Requires -Version 7.0
# Isolated Windows 11 / PowerShell 7 two-service live integration and failure test.
param([string]$Python='python',[int]$EmitPort=18001,[int]$BrainPort=18281,[string]$ReuseWorkspace='')
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$original=@{}
$envKeys=@('KINDRED_INTERNAL_SERVICE_KEY','BRAINSTEM_AWARENESS_KEY','KINDRED_EMIT_CORE_URL','KINDRED_SQLITE_PATH','KINDRED_STATE_DB','KINDRED_CLOUD_USE_LOCAL_STORE')
foreach($k in $envKeys){$original[$k]=[Environment]::GetEnvironmentVariable($k,'Process')}
$root=if($ReuseWorkspace){ (Resolve-Path -LiteralPath $ReuseWorkspace -ErrorAction Stop).Path }else{ Join-Path ([IO.Path]::GetTempPath()) ('Kindred-Workforce-E2E-'+[guid]::NewGuid().ToString('N')) }
$er=Join-Path $root 'EMIT'; $br=Join-Path $root 'BRAINSTEM'
$run=Join-Path (Join-Path $root 'runs') ([guid]::NewGuid().ToString('N'))
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
  $limit=(Get-Date).AddSeconds(180)
  $lastError=''
  $attempts=0
  while((Get-Date) -lt $limit){
    if($proc.HasExited){
      $log=if(Test-Path -LiteralPath $err){(Get-Content -LiteralPath $err -Tail 40) -join [Environment]::NewLine}else{'No server log'}
      throw "Service exited while probing $url. Log: $log"
    }
    try{
      $attempts++
      $reply=Invoke-WebRequest -Uri $url -NoProxy -TimeoutSec 15 -SkipHttpErrorCheck -ErrorAction Stop
      if([int]$reply.StatusCode -ne 200){
        $lastError="HTTP $([int]$reply.StatusCode)"
      }else{
        $health=ConvertFrom-Json -InputObject ([string]$reply.Content) -ErrorAction Stop
        Write-Host "HTTP 200 and valid JSON from $url (attempt $attempts)"
        return $health
      }
    }catch{
      $lastError=$_.Exception.Message
      if($attempts -eq 1 -or $attempts % 5 -eq 0){Write-Warning "Readiness probe $url attempt $attempts : $lastError"}
    }
    Start-Sleep -Milliseconds 750
  }
  $log=if(Test-Path -LiteralPath $err){(Get-Content -LiteralPath $err -Tail 60) -join [Environment]::NewLine}else{'No server log'}
  throw "Service readiness timed out for $url after $attempts attempts. Last client error: $lastError. Server log: $log"
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
  New-Item -ItemType Directory -Path $run -Force | Out-Null
  $env:KINDRED_SQLITE_PATH=Join-Path $run 'emit-tests.db'
  $env:KINDRED_STATE_DB=Join-Path $run 'brainstem-tests.db'
  $env:KINDRED_CLOUD_USE_LOCAL_STORE='1'
  & git --version | Out-Null; VerifyExit 'git'
  $Python=Resolve-CompatiblePython $Python
  Write-Host "Using compatible interpreter: $Python"
  & $Python -c "import sys; print('Python',sys.version.split()[0])"; VerifyExit 'Python verification'
  if($ReuseWorkspace){
    Write-Host "Reusing already-installed integration environment: $root"
    foreach($expected in @((Join-Path $er '.venv\Scripts\python.exe'),(Join-Path $br '.venv\Scripts\python.exe'),(Join-Path $er 'cloud\api\main.py'),(Join-Path $br 'brainstem\runtime\app.py'))){
      if(-not (Test-Path -LiteralPath $expected -PathType Leaf)){throw "Cannot reuse incomplete workspace: $expected"}
    }
    & git -C $er pull --ff-only
    VerifyExit 'Update isolated EMIT branch'
    & git -C $br pull --ff-only
    VerifyExit 'Update isolated BRAINSTEM branch'
    $checkedBrainPython=Join-Path $br '.venv\Scripts\python.exe'
    $checkedEmitPython=Join-Path $er '.venv\Scripts\python.exe'
    Push-Location $br
    try {
      & $checkedBrainPython -m pip install -e '.[dev]'
      VerifyExit 'Updated BRAINSTEM orchestration dependencies'
      & $checkedBrainPython -m pytest -q tests/test_workforce_awareness.py tests/test_workforce_orchestration.py tests/test_causal_mesh.py tests/test_autopoietic_fabric.py
      VerifyExit 'Updated BRAINSTEM workforce and orchestration tests'
    } finally { Pop-Location }
    Push-Location $er
    try {
      & $checkedEmitPython -m pytest -q cloud/tests/test_worker_inventory.py cloud/tests/test_workforce_execution.py cloud/tests/test_causal_attestation.py cloud/tests/test_causal_batch.py
      VerifyExit 'Updated EMIT worker execution tests'
    } finally { Pop-Location }
  }else{
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
    & $ePython -m pytest -q cloud/tests/test_worker_inventory.py cloud/tests/test_workforce_execution.py cloud/tests/test_causal_attestation.py cloud/tests/test_causal_batch.py; VerifyExit 'EMIT tests'
  }finally{Pop-Location}
  Push-Location $br
  try{
    & $bPython -m pip install -e '.[dev]'; VerifyExit 'BRAINSTEM install'
    & $bPython -m pip check; VerifyExit 'BRAINSTEM pip check'
    & $bPython -m pytest -q tests/test_workforce_awareness.py tests/test_workforce_orchestration.py tests/test_causal_mesh.py tests/test_autopoietic_fabric.py; VerifyExit 'BRAINSTEM tests'
  }finally{Pop-Location}
  }
  $ePython=Join-Path $er '.venv\Scripts\python.exe'
  $bPython=Join-Path $br '.venv\Scripts\python.exe'
  $bytes=[byte[]]::new(32);[Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
  $env:KINDRED_INTERNAL_SERVICE_KEY=[Convert]::ToHexString($bytes)
  [Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
  $env:BRAINSTEM_AWARENESS_KEY=[Convert]::ToHexString($bytes)
  $env:KINDRED_EMIT_CORE_URL="http://127.0.0.1:$EmitPort"
  $env:KINDRED_SQLITE_PATH=Join-Path $run 'emit-live.db'
  $env:KINDRED_STATE_DB=Join-Path $run 'brainstem-live.db'
  $env:KINDRED_CLOUD_USE_LOCAL_STORE='1'
  $eErr=Join-Path $run 'emit.err.log'; $bErr=Join-Path $run 'brainstem.err.log'
  $ep=Start-Process -FilePath $ePython -WorkingDirectory $er -ArgumentList @('-m','uvicorn','cloud.api.main:app','--host','127.0.0.1','--port',"$EmitPort") -PassThru -RedirectStandardOutput (Join-Path $run 'emit.out.log') -RedirectStandardError $eErr
  $eh=WaitUrl "http://127.0.0.1:$EmitPort/health" $ep $eErr
  if(-not $eh.foundation.foundation_ready){throw "EMIT foundation not ready: $($eh|ConvertTo-Json -Depth 8)"}
  $bp=Start-Process -FilePath $bPython -WorkingDirectory $br -ArgumentList @('-m','uvicorn','brainstem.runtime.app:app','--host','127.0.0.1','--port',"$BrainPort") -PassThru -RedirectStandardOutput (Join-Path $run 'brainstem.out.log') -RedirectStandardError $bErr
  $null=WaitUrl "http://127.0.0.1:$BrainPort/health" $bp $bErr
  $eBase="http://127.0.0.1:$EmitPort";$bBase="http://127.0.0.1:$BrainPort"
  $unauthorized = Invoke-WebRequest -Uri "$eBase/runtime/workers/inventory" -NoProxy -TimeoutSec 15 -SkipHttpErrorCheck -ErrorAction Stop
  if ([int]$unauthorized.StatusCode -ne 401) {
    throw "EMIT inventory must reject unauthenticated access with 401; observed HTTP $([int]$unauthorized.StatusCode)"
  }
  Write-Host 'EMIT unauthenticated inventory denied as expected (HTTP 401)'
  $ehdr=@{'X-Kindred-Internal-Key'=$env:KINDRED_INTERNAL_SERVICE_KEY}
  $bhdr=@{'X-Brainstem-Awareness-Key'=$env:BRAINSTEM_AWARENESS_KEY}
  $i=Invoke-RestMethod "$eBase/runtime/workers/inventory" -Headers $ehdr -NoProxy -TimeoutSec 20
  if($i.schema_version -ne 'kindred.workforce.inventory.v1' -or $i.summary.configured_lane_definitions -ne 14 -or $i.summary.online_lane_workers -lt 1){throw 'EMIT live worker contract failed'}
  $s=Invoke-RestMethod "$bBase/awareness/sync" -Method Post -Headers $bhdr -NoProxy -TimeoutSec 20
  $w=Invoke-RestMethod "$bBase/awareness/workers" -NoProxy -TimeoutSec 20
  $world=Invoke-RestMethod "$bBase/world" -NoProxy -TimeoutSec 20
  Write-Host ("EMIT online workers: {0}; EMIT reported instances: {1}; BRAINSTEM online workers: {2}; BRAINSTEM records: {3}; sync status: {4}" -f $i.summary.online_lane_workers,$i.summary.observed_lane_instances,$w.summary.online_workers,$w.summary.observed_worker_records,$s.status)
  if ($s.status -eq 'unavailable' -or $s.status -eq 'not_configured') {
    $syncError = if ($null -ne $s.PSObject.Properties['error']) {$s.error} else {'No sync error supplied'}
    throw "BRAINSTEM could not read EMIT inventory: $syncError"
  }
  if($s.status -ne 'observations_available') {
    throw "BRAINSTEM returned unexpected synchronization state: $($s.status)"
  }
  if($w.summary.online_workers -ne $i.summary.online_lane_workers){
    $emittedWorkers=@($i.workers | Where-Object {$_.status -eq 'online'} | ForEach-Object {$_.worker_id})
    $observedWorkers=@($w.workers | Where-Object {$_.status -eq 'online'} | ForEach-Object {$_.worker_id})
    $missing=@($emittedWorkers | Where-Object {$_ -notin $observedWorkers})
    $extra=@($observedWorkers | Where-Object {$_ -notin $emittedWorkers})
    throw "Live worker mismatch: EMIT=$($i.summary.online_lane_workers), BRAINSTEM=$($w.summary.online_workers); missing=$($missing -join ','); extra=$($extra -join ',')"
  }
  if($world.operational_awareness.source_of_truth -ne 'brainstem_local_state'){throw 'BRAINSTEM cognition world not connected'}
  if($w.summary.registered_emit_agent_records -ne $i.summary.registered_agent_records){throw 'Agent registration distinction failed'}
  # Exercise the real queue execution path, not merely liveness or mocks.
  $contracts=Invoke-RestMethod "$bBase/orchestration/contracts" -Headers $bhdr -NoProxy -TimeoutSec 20
  if(@($contracts | Where-Object {$_.contract_id -eq 'runtime.snapshot@v2' -and $_.verification_tier -eq 'signal_lane_causal'}).Count -ne 1){throw 'Required PoECL execution contract not registered'}
  $dispatchBody=@{
    idempotency_key='e2e-snapshot-'+[guid]::NewGuid().ToString('N')
    contract_id='runtime.snapshot@v2'
    payload=@{}
    lease_seconds=60
  } | ConvertTo-Json -Depth 8 -Compress
  $first=Invoke-RestMethod "$bBase/orchestration/dispatch" -Method Post -Headers $bhdr -NoProxy -TimeoutSec 45 -ContentType 'application/json' -Body $dispatchBody
  if($first.status -ne 'verified_complete' -or -not $first.verified_receipt.signature){
    throw "No verified execution receipt: $($first | ConvertTo-Json -Depth 12)"
  }
  if($first.verified_receipt.causal_proof.schema_version -ne 'kindred.poecl.process_trace.v1' -or
     -not $first.verified_receipt.causal_proof.chain_hash){
    throw 'PoECL causal receipt missing or malformed'
  }
  $ledger=Invoke-RestMethod "$eBase/runtime/workers/causal/verify" -Headers $ehdr -NoProxy -TimeoutSec 30
  if(-not $ledger.valid -or $ledger.rows_checked -lt 1){
    throw "EMIT causal ledger verification failed: $($ledger | ConvertTo-Json -Depth 8)"
  }
  Write-Host "EMIT PoECL chain verified: $($ledger.rows_checked) receipt(s); head=$($ledger.head)"
  $replayed=Invoke-RestMethod "$bBase/orchestration/dispatch" -Method Post -Headers $bhdr -NoProxy -TimeoutSec 30 -ContentType 'application/json' -Body $dispatchBody
  if($replayed.task_id -ne $first.task_id -or $replayed.verified_receipt.signature -ne $first.verified_receipt.signature){
    throw 'Idempotent task replay did not return the same verified receipt'
  }
  $status=Invoke-RestMethod "$bBase/orchestration/tasks/$($first.task_id)" -Headers $bhdr -NoProxy -TimeoutSec 20
  if($status.status -ne 'verified_complete'){throw 'Verified task not persisted in BRAINSTEM'}
  $summary=Invoke-RestMethod "$bBase/orchestration/cognitive-summary" -Headers $bhdr -NoProxy -TimeoutSec 20
  $worldAfter=Invoke-RestMethod "$bBase/world" -NoProxy -TimeoutSec 20
  if(@($summary.verified_outcomes | Where-Object {$_.task_id -eq $first.task_id}).Count -ne 1 -or
     @($worldAfter.workforce_orchestration.verified_outcomes | Where-Object {$_.task_id -eq $first.task_id}).Count -ne 1){
    throw 'Verified execution outcome not visible in BRAINSTEM cognition'
  }
  $kacfOutcome=@($worldAfter.workforce_orchestration.verified_outcomes | Where-Object {$_.task_id -eq $first.task_id})[0]
  if($kacfOutcome.causal_chain_hash -ne $first.verified_receipt.causal_proof.chain_hash){
    throw 'BRAINSTEM cognitive world does not preserve verified PoECL chain digest'
  }
  Write-Host "Real contract-bound worker execution verified: $($first.task_id), worker=$($first.assigned_worker_id)"
  Write-Host 'Live sync and signed execution passed. Testing worker loss; waiting 65 seconds for observation TTL.'
  Stop-Process -Id $ep.Id -Force; $null=$ep.WaitForExit(10000)
  Start-Sleep -Seconds 65
  $stale=Invoke-RestMethod "$bBase/awareness/workers" -NoProxy -TimeoutSec 20
  if($stale.summary.online_workers -ne 0){throw 'Stale workers incorrectly online'}
  $stillFresh=@($stale.workers | Where-Object {$_.source -eq 'kindred_emit_core' -and $_.status -ne 'stale'})
  if($stillFresh.Count -gt 0){throw 'Worker loss was not marked stale'}
  [pscustomobject]@{result='PASS';observed_lane_workers=$i.summary.online_lane_workers;registered_agent_records=$i.summary.registered_agent_records;online_after_loss=$stale.summary.online_workers;persisted_records=$stale.summary.observed_worker_records;verified_execution_task=$first.task_id;poecl_chain_head=$ledger.head;logs=$run} | Format-List
}finally{
  foreach($p in @($ep,$bp)){if($null -ne $p){try{if(-not $p.HasExited){Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue}}catch{};$p.Dispose()}}
  foreach($k in $envKeys){[Environment]::SetEnvironmentVariable($k,$original[$k],'Process')}
  Write-Host "Reusable source workspace: $root"
  Write-Host "Isolated run databases and diagnostic logs: $run"
}
