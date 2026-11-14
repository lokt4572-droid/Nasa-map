# MARS EXPLORER - stop the backend and frontend servers of THIS project only.
param([switch]$Quiet)
$Root = Split-Path -Parent $PSScriptRoot
$escaped = [regex]::Escape($Root)

$procs = @(Get-CimInstance Win32_Process | Where-Object {
    $_.CommandLine -and (
        ($_.CommandLine -match $escaped -and $_.CommandLine -match 'runserver|vite') -or
        ($_.Name -eq 'cmd.exe' -and $_.CommandLine -match 'MARS EXPLORER (backend|frontend)')
    )
})
# Also anything listening on our ports that belongs to this project folder (e.g. Django's reloader child).
foreach ($port in 8000, 5173) {
    Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | ForEach-Object {
        $p = Get-CimInstance Win32_Process -Filter "ProcessId=$($_.OwningProcess)"
        if ($p -and $p.CommandLine -match $escaped) { $procs += $p }
    }
}

$ids = $procs | Select-Object -ExpandProperty ProcessId -Unique
foreach ($id in $ids) { taskkill /PID $id /T /F 2>$null | Out-Null }
if (-not $Quiet) {
    if ($ids) { Write-Host "Stopped MARS EXPLORER servers ($($ids.Count) process(es))." -ForegroundColor Green }
    else { Write-Host "MARS EXPLORER was not running." }
    Start-Sleep -Seconds 2
}
