param([switch]$Browser)

$ErrorActionPreference = 'Stop'
Push-Location (Join-Path $PSScriptRoot '..')
try {
    & .venv\Scripts\python -m pip check
    if ($LASTEXITCODE -ne 0) { throw 'Python dependency conflicts found' }
    & .venv\Scripts\python -m pytest tests -q -p no:cacheprovider
    if ($LASTEXITCODE -ne 0) { throw 'Backend tests failed' }
    & npm.cmd test
    if ($LASTEXITCODE -ne 0) { throw 'Frontend tests failed' }
    & npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed' }
    if ($Browser) {
        & npm.cmd run test:assistant
        if ($LASTEXITCODE -ne 0) { throw 'Browser regression checks failed' }
    }
} finally {
    Pop-Location
}
