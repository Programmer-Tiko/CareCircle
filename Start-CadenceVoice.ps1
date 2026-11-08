param(
    [string]$PythonPath = '',
    [int]$Port = 8001,
    [string]$SettingsFile = '',
    [string]$Model = 'base.en',
    [switch]$OfflineQuestionDemo
)
$ErrorActionPreference = 'Stop'
$voiceRepoRoot = $PSScriptRoot
if (-not $PythonPath) { $PythonPath = Join-Path $voiceRepoRoot '.venv/Scripts/python.exe' }
if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) { throw 'Provide -PythonPath to a virtual environment with backend requirements and requirements-asr.txt installed.' }
$voicePythonRoot = Split-Path -Parent (Split-Path -Parent (Resolve-Path -LiteralPath $PythonPath).Path)
$voiceCachePath = Join-Path $voicePythonRoot 'whisper-cache'
$voiceDockerConfig = Join-Path $voicePythonRoot 'cadence-docker-client'
New-Item -ItemType Directory -Path $voiceDockerConfig -Force | Out-Null
$voiceContainer = 'cadence-voice-first-dev'
$voiceVolume = 'cadence-voice-first-dev-data'
$voiceDatabase = 'cadence_voice_first'
if ($OfflineQuestionDemo) {
    $voiceContainer = 'cadence-voice-first-demo'
    $voiceVolume = 'cadence-voice-first-demo-data'
    $voiceDatabase = 'cadence_voice_first_demo'
}
$voiceContainers = & docker --config $voiceDockerConfig ps -a --filter "name=^/$voiceContainer$" --format '{{.Names}}'
if ($LASTEXITCODE -ne 0) { throw 'Start Docker Desktop and retry.' }
if ($voiceContainers -contains $voiceContainer) {
    & docker --config $voiceDockerConfig start $voiceContainer | Out-Null
} else {
    & docker --config $voiceDockerConfig run -d --name $voiceContainer -e POSTGRES_HOST_AUTH_METHOD=trust -e "POSTGRES_DB=$voiceDatabase" -p 127.0.0.1::5432 --mount "type=volume,source=$voiceVolume,target=/var/lib/postgresql/data" timescale/timescaledb:latest-pg17 | Out-Null
}
if ($LASTEXITCODE -ne 0) { throw 'Could not start the dedicated voice development database. Existing demo databases were not changed.' }
$voiceReady = $false
for ($voiceAttempt = 0; $voiceAttempt -lt 30; $voiceAttempt++) {
    & docker --config $voiceDockerConfig exec $voiceContainer pg_isready -U postgres -d $voiceDatabase *> $null
    if ($LASTEXITCODE -eq 0) { $voiceReady = $true; break }
    Start-Sleep -Seconds 1
}
if (-not $voiceReady) { throw 'Voice development database is not ready.' }
$voiceMapping = & docker --config $voiceDockerConfig port $voiceContainer 5432/tcp
$voiceDbPort = ($voiceMapping.Trim() -split ':')[-1]
$voiceDbUrl = 'postgresql://postgres@127.0.0.1:' + $voiceDbPort + '/' + $voiceDatabase
$voiceArguments = @((Join-Path $voiceRepoRoot 'scripts/run_voice.py'), '--port', "$Port", '--db-url', $voiceDbUrl, '--cache-path', $voiceCachePath, '--model', $Model)
if ($SettingsFile) { $voiceArguments += @('--settings-file', (Resolve-Path -LiteralPath $SettingsFile).Path) }
if ($OfflineQuestionDemo) { $voiceArguments += '--offline-question-demo' }
Write-Output "Database volume: $voiceVolume (retained across container restarts). Do not remove this volume if you want to keep your development records."
& $PythonPath @voiceArguments
