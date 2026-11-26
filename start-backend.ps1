$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONUTF8 = '1'
# Pick up FFmpeg installed after this terminal was opened.
$env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User') + ';' + $env:Path
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    throw 'FFmpeg is missing. Install it with: winget install --id Gyan.FFmpeg -e'
}
& "$PSScriptRoot\.venv\Scripts\python.exe" -c 'import whisper'
if ($LASTEXITCODE -ne 0) { throw 'Install backend dependencies: .\.venv\Scripts\python.exe -m pip install -r requirements.txt' }
& "$PSScriptRoot\.venv\Scripts\python.exe" -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
