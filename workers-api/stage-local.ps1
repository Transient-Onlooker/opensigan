param(
    [Parameter(Mandatory = $true)][string]$WranglerModules
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$source = Join-Path $root '..\backend\timetable.py'
$neisSource = Join-Path $root '..\backend\neis.py'
$venv = Join-Path $root '.venv-workers'
$vendor = Join-Path $root 'python_modules'
$project = Join-Path $root 'pyproject.toml'
$lock = Join-Path $root 'pylock.toml'
$latest = @((Get-Item $project).LastWriteTimeUtc, (Get-Item $lock).LastWriteTimeUtc) | Sort-Object -Descending | Select-Object -First 1
foreach ($token in @((Join-Path $venv '.synced'), (Join-Path $vendor '.synced'))) {
    if ((Get-Item $token).LastWriteTimeUtc -lt $latest -or (Get-Content $token -Raw).Trim() -ne '1.17.9') {
        throw 'Existing workers-api dependencies are not synced with this project and pywrangler 1.17.9.'
    }
}
$modules = (Resolve-Path -LiteralPath $WranglerModules).Path
if (-not (Test-Path -LiteralPath (Join-Path $modules '.bin\wrangler.cmd'))) {
    throw 'WranglerModules must contain .bin\wrangler.cmd.'
}
$stage = Join-Path $root ('.runtime\stage-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path (Join-Path $stage 'backend') -Force | Out-Null
Copy-Item -LiteralPath $source -Destination (Join-Path $stage 'backend\timetable.py')
Copy-Item -LiteralPath $neisSource -Destination (Join-Path $stage 'backend\neis.py')
foreach ($name in @('worker.py', 'd1_cache.py', 'schema.sql', 'wrangler.toml', 'pyproject.toml', 'pylock.toml')) {
    Copy-Item -LiteralPath (Join-Path $root $name) -Destination (Join-Path $stage $name)
}
Copy-Item -LiteralPath $vendor -Destination (Join-Path $stage 'python_modules') -Recurse
New-Item -ItemType Junction -Path (Join-Path $stage '.venv-workers') -Target $venv | Out-Null
New-Item -ItemType Junction -Path (Join-Path $stage 'node_modules') -Target $modules | Out-Null
Write-Output $stage
