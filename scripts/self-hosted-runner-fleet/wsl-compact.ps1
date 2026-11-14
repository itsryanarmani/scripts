<#
.SYNOPSIS
  Shrink the WSL2 virtual disk of a runner host, but only when no job is running.

.DESCRIPTION
  WSL2 never gives disk space back to Windows on its own. After you clean files inside the
  distro, the ext4.vhdx file stays large. This script waits for the fleet to be idle, shuts
  WSL down, compacts the disk file with diskpart, and starts WSL again through the keepalive
  scheduled task.

  Run it from a scheduled task with highest privileges, as the same account that owns the
  WSL distribution (it reads that account's registry). SYSTEM does not work. It needs
  administrator rights.

  Shutting WSL down kills any running job. The script counts jobs first and waits up to
  -WaitMinutes. If it cannot read the job count, it treats the fleet as busy. If a job is
  still running after the wait, it exits with code 2 and changes nothing. There is a short
  gap between the check and the shutdown. A job that starts in that gap fails and you re-run
  it.

  After the shutdown the script always detaches the disk and starts WSL again, even when
  compaction failed. A failed compaction exits with code 1.

.PARAMETER Distro          WSL distribution name. Default: Ubuntu.
.PARAMETER KeepaliveTask   Scheduled task that holds WSL open. It is started after compaction.
.PARAMETER WaitMinutes     How long to wait for an idle fleet. Default: 90.
.PARAMETER DryRun          Report what would happen. Change nothing.
#>
param(
  [string]$Distro = 'Ubuntu',
  [string]$KeepaliveTask = '',
  [int]$WaitMinutes = 90,
  [switch]$DryRun
)
$ErrorActionPreference = 'Stop'

function Get-VhdPath([string]$name) {
  $key = Get-ChildItem 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Lxss' |
    Where-Object { (Get-ItemProperty $_.PSPath).DistributionName -eq $name } | Select-Object -First 1
  if (-not $key) { throw "Distro not found: $name" }
  $base = (Get-ItemProperty $key.PSPath).BasePath -replace '^\\\\\?\\', ''
  $vhd = Join-Path $base 'ext4.vhdx'
  if (-not (Test-Path $vhd)) { throw "Disk file not found: $vhd" }
  return $vhd
}

# Returns the number of running jobs, or -1 when the count cannot be read.
function Get-BusyWorkers([string]$name) {
  try {
    $out = (& wsl.exe -d $name -u root -- bash -c 'pgrep -fc "Runner\.Worker" || true' 2>$null | Out-String).Trim()
  } catch { return -1 }
  if ($out -match '^\d+$') { return [int]$out }
  return -1
}

function Invoke-DiskPart([string[]]$lines) {
  $f = Join-Path $env:TEMP ('wsl-compact-' + [guid]::NewGuid().ToString('N') + '.diskpart')
  try {
    $lines | Set-Content -Encoding ascii $f
    $out = & diskpart.exe /s $f | Out-String
    return [pscustomobject]@{ Code = $LASTEXITCODE; Output = $out }
  } finally { Remove-Item $f -ErrorAction SilentlyContinue }
}

# Start WSL and keep it up. Without a keepalive task, hold the VM open with a process that
# does not exit. That process ends at logoff, so a real fleet needs the keepalive task or
# `vmIdleTimeout=-1` in .wslconfig.
function Start-Wsl {
  if ($KeepaliveTask) {
    try { Start-ScheduledTask -TaskName $KeepaliveTask; return } catch { "Keepalive task failed: $($_.Exception.Message). Starting WSL directly." }
  }
  Start-Process wsl.exe -ArgumentList "-d $Distro -u root -- sleep infinity" -WindowStyle Hidden
}

# True when the distro answers a command. Retries, because boot takes a few seconds.
function Test-WslUp {
  for ($i = 0; $i -lt 12; $i++) {
    # wsl.exe may write to stderr while it boots. Under $ErrorActionPreference = 'Stop'
    # that would end the script, so catch it and retry.
    try { $out = (& wsl.exe -d $Distro -u root -- echo up 2>$null | Out-String).Trim() } catch { $out = '' }
    if ($out -eq 'up') { return $true }
    Start-Sleep -Seconds 5
  }
  return $false
}

$vhd = Get-VhdPath $Distro
$before = [math]::Round((Get-Item $vhd).Length / 1GB, 1)
"Disk file: $vhd  size: $before GB"

$deadline = (Get-Date).AddMinutes($WaitMinutes)
while ($true) {
  $busy = Get-BusyWorkers $Distro
  if ($busy -eq 0) { break }
  if ((Get-Date) -gt $deadline) {
    if ($busy -lt 0) { "Could not read the job count after $WaitMinutes min. Nothing changed." }
    else { "Still $busy job(s) after $WaitMinutes min. Nothing changed." }
    exit 2
  }
  if ($busy -lt 0) { "Waiting: could not read the job count." } else { "Waiting: $busy job(s) running." }
  Start-Sleep -Seconds 60
}

if ($DryRun) { "Dry run: fleet is idle. Would shut down WSL and compact $vhd."; exit 0 }

$failed = $false
& wsl.exe --shutdown
try {
  $until = (Get-Date).AddMinutes(3)
  while ($true) {
    try { $fs = [System.IO.File]::Open($vhd, 'Open', 'Read', 'None'); $fs.Close(); break }
    catch { if ((Get-Date) -gt $until) { throw "Disk file still in use after shutdown." }; Start-Sleep -Seconds 3 }
  }
  $r = Invoke-DiskPart @("select vdisk file=`"$vhd`"", 'attach vdisk readonly', 'compact vdisk', 'exit')
  $r.Output | Write-Output
  if ($r.Code -ne 0) { throw "diskpart failed with code $($r.Code)." }
}
catch { $failed = $true; "Compaction failed: $($_.Exception.Message)" }
finally {
  # Always detach, then always bring WSL back, even when compaction failed.
  # A disk left attached keeps WSL from booting. Detach can fail when the earlier attach
  # failed, so read the result and report it.
  $detach = $null
  try { $detach = Invoke-DiskPart @("select vdisk file=`"$vhd`"", 'detach vdisk', 'exit') }
  catch { "Detach failed: $($_.Exception.Message)"; $failed = $true }
  if ($detach -and $detach.Code -ne 0) { "Detach reported code $($detach.Code): $($detach.Output.Trim())"; $failed = $true }
  Start-Wsl
}

$after = [math]::Round((Get-Item $vhd).Length / 1GB, 1)
# Check the outcome, not the steps: the distro must answer after the restart.
if (-not (Test-WslUp)) { "WSL did not come back after compaction. Disk file is $after GB. Check the disk is detached."; exit 1 }
if ($failed) { "Compaction failed. Disk file is $after GB. WSL is running."; exit 1 }
"Compacted: $before GB -> $after GB (freed $([math]::Round($before - $after, 1)) GB). WSL is running."
