param(
    [Parameter(Mandatory = $true)][string]$Pywrangler
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$backend = Join-Path $root '..\backend'
$pywranglerPath = (Resolve-Path -LiteralPath $Pywrangler).Path
$version = (& $pywranglerPath --version).Trim()
if ($version -ne 'pywrangler, version 1.17.9') {
    throw "Expected pinned pywrangler 1.17.9, got $version."
}
$toolDirectory = Split-Path $pywranglerPath
$uv = Join-Path $toolDirectory 'uv.exe'
if ((& $uv --version) -notmatch '^uv 0\.13\.4\b') {
    throw 'Expected uv 0.13.4 next to pywrangler.'
}
if ((& node --version).Trim() -ne 'v26.13.0' -or (& npm --version).Trim() -ne '12.0.2') {
    throw 'Expected Node.js 26.13.0 and npm 12.0.2.'
}
foreach ($entry in @(
    @('pycomcigan-1.4.3-py3-none-any.whl', '9a3aa5c8eafd95d29f574941b4264f26480e7fc51ec5be45e37a2462b7dd85d9'),
    @('pycryptodomex-3.24.2-cp37-abi3-pyemscripten_2026_0_wasm32.whl', 'f2c5fdc9fe8ba8ea5b827dc04fe06ad2d47e96ecbba58494bb6d5794439602b5')
)) {
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $root "wheelhouse\$($entry[0])")).Hash -ne $entry[1]) {
        throw "Wheel hash mismatch: $($entry[0])"
    }
}

$stage = Join-Path $root ('.runtime\repro-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path (Join-Path $stage 'backend'), (Join-Path $stage 'wheelhouse') -Force | Out-Null
foreach ($name in @('worker.py', 'd1_cache.py', 'schema.sql', 'wrangler.toml', 'pyproject.toml', 'uv.lock', 'package.json', 'package-lock.json')) {
    Copy-Item -LiteralPath (Join-Path $root $name) -Destination (Join-Path $stage $name)
}
Copy-Item -LiteralPath (Join-Path $root 'pylock.seed.toml') -Destination (Join-Path $stage 'pylock.toml')
# Resolve the copied wheel through the stage's find-links directory. A direct
# path source makes pywrangler force --refresh-package, which uv rejects offline.
$stageProject = Join-Path $stage 'pyproject.toml'
$projectText = [IO.File]::ReadAllText($stageProject)
$updatedProject = [regex]::Replace($projectText, '(?m)^\[tool\.uv\.sources\]\r?\npycomcigan = \{ path = "wheelhouse/pycomcigan-1\.4\.3-py3-none-any\.whl" \}\r?\n\r?\n', '')
if ($updatedProject -eq $projectText) { throw 'Expected pycomcigan path source not found in pyproject.toml.' }
$projectText = $updatedProject
[IO.File]::WriteAllText($stageProject, $projectText, [Text.UTF8Encoding]::new($false))
foreach ($name in @('timetable.py', 'neis.py')) {
    Copy-Item -LiteralPath (Join-Path $backend $name) -Destination (Join-Path $stage "backend\$name")
}
foreach ($name in @('pycomcigan-1.4.3-py3-none-any.whl', 'pycryptodomex-3.24.2-cp37-abi3-pyemscripten_2026_0_wasm32.whl')) {
    Copy-Item -LiteralPath (Join-Path $root "wheelhouse\$name") -Destination (Join-Path $stage 'wheelhouse')
}

# Rebase the staged lock's wheel URI to its copied wheelhouse.
$runtimeLock = Join-Path $stage 'pylock.toml'
$lockText = [IO.File]::ReadAllText($runtimeLock)
$wheel = Join-Path $stage 'wheelhouse\pycryptodomex-3.24.2-cp37-abi3-pyemscripten_2026_0_wasm32.whl'
$wheelUri = ([Uri]$wheel).AbsoluteUri
$lockText = [regex]::Replace($lockText, 'file:[^"\r\n]*/pycryptodomex-3\.24\.2-cp37-abi3-pyemscripten_2026_0_wasm32\.whl', $wheelUri)
if (-not $lockText.Contains($wheelUri) -or -not $lockText.Contains('path = "wheelhouse/pycomcigan-1.4.3-py3-none-any.whl"')) {
    throw 'The runtime lock seed does not contain the expected wheel paths.'
}
[IO.File]::WriteAllText($runtimeLock, $lockText, [Text.UTF8Encoding]::new($false))

$variables = @('npm_config_offline', 'UV_OFFLINE', 'UV_PYTHON_DOWNLOADS', 'UV_PYTHON_PREFERENCE', 'WRANGLER_SEND_METRICS', 'CLOUDFLARE_LOAD_DEV_VARS_FROM_DOT_ENV', 'CLOUDFLARE_INCLUDE_PROCESS_ENV', 'PATH', 'UV_CACHE_DIR', 'UV_PYTHON_INSTALL_DIR', 'TEMP', 'TMP', 'XDG_CONFIG_HOME')
$originalEnvironment = @{}
foreach ($name in $variables) { $originalEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, 'Process') }
try {
$env:npm_config_offline = 'false'
$env:UV_OFFLINE = '0'
$env:UV_PYTHON_DOWNLOADS = 'automatic'
$env:UV_PYTHON_PREFERENCE = 'only-managed'
$env:WRANGLER_SEND_METRICS = 'false'
$env:CLOUDFLARE_LOAD_DEV_VARS_FROM_DOT_ENV = 'false'
$env:CLOUDFLARE_INCLUDE_PROCESS_ENV = 'false'
$env:PATH = "$toolDirectory;$env:PATH"
$env:UV_CACHE_DIR = Join-Path $stage 'uv-cache-empty'
$env:UV_PYTHON_INSTALL_DIR = Join-Path $stage 'uv-python'
$env:TEMP = Join-Path $stage 'tmp'
$env:TMP = $env:TEMP
$env:XDG_CONFIG_HOME = Join-Path $stage 'config'
New-Item -ItemType Directory -Path $env:TEMP, $env:XDG_CONFIG_HOME, $env:UV_PYTHON_INSTALL_DIR, $env:UV_CACHE_DIR | Out-Null
Write-Host "Preparing $stage"
$stageNpmCache = Join-Path $stage 'npm-cache-empty'
New-Item -ItemType Directory -Path $stageNpmCache | Out-Null
Push-Location $stage
try {
    npm ci --cache $stageNpmCache --ignore-scripts --no-audit --no-fund | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'Pinned Wrangler dependency installation failed.' }
    & $uv python install 3.14.7 | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'Pinned CPython installation failed.' }
    & $pywranglerPath sync | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'Workers Python dependency sync failed.' }
}
finally {
    Pop-Location
}
$bundle = Join-Path $stage 'bundle'
New-Item -ItemType Directory -Path $bundle | Out-Null
foreach ($name in @('worker.py', 'd1_cache.py', 'schema.sql', 'wrangler.toml', 'backend', 'python_modules')) {
    Copy-Item -LiteralPath (Join-Path $stage $name) -Destination $bundle -Recurse
}
Write-Output $stage
}
finally {
    foreach ($name in $variables) { [Environment]::SetEnvironmentVariable($name, $originalEnvironment[$name], 'Process') }
}
