[CmdletBinding()]
param(
    [ValidateSet('Setup','Doctor','Start','Stop','Infra','Backend','Frontend','Devtools','Browsers','Lint','Test','Debug','InstallExtensions')]
    [string]$Action = 'Doctor',
    [ValidateSet('Auto','Kiro','VSCode')][string]$Editor = 'Auto',
    [switch]$DryRun,
    [switch]$Build
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$compose = @('compose', '-p', 'dataanalyst', '-f', (Join-Path $repo 'docker-compose.yml'))
$toolsCompose = $compose + @('-f', (Join-Path $repo '.devcontainer/compose.yml'))
$verifyCompose = @('compose', '-p', 'dataanalyst-verify', '-f', (Join-Path $repo 'docker-compose.verify.yml'))

function Invoke-DockerChecked {
    param([string[]]$DockerArgs)
    if ($DryRun -and $Action -ne 'Doctor') {
        Write-Output ('DRY RUN: docker ' + ($DockerArgs -join ' '))
        return
    }
    & docker @DockerArgs
    if ($LASTEXITCODE -ne 0) { throw "Docker step failed (exit $LASTEXITCODE)." }
}

function Install-EditorExtensions {
    $editorCli = if ($Editor -eq 'Kiro' -or ($Editor -eq 'Auto' -and (Get-Command kiro -ErrorAction SilentlyContinue))) { 'kiro' } else { 'code' }
    if (-not (Get-Command $editorCli -ErrorAction SilentlyContinue)) { throw "Editor CLI $editorCli not found; see docs/DEVELOPMENT_SETUP.md." }
    $helpText = & $editorCli --help | Out-String
    if ($helpText -notmatch '--install-extension' -or $helpText -notmatch '--list-extensions') { throw 'Editor CLI does not support extension management.' }
    $ids = @('ms-python.python','ms-python.debugpy','charliermarsh.ruff','dbaeumer.vscode-eslint','esbenp.prettier-vscode','redhat.vscode-yaml','ms-azuretools.vscode-containers')
    $ids += if ($editorCli -eq 'kiro') { 'detachhead.basedpyright' } else { 'ms-python.vscode-pylance' }
    $installed = @(& $editorCli --list-extensions)
    if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect installed extensions.' }
    foreach ($id in $ids) {
        if ($id -in $installed) { Write-Output "Already installed: $id"; continue }
        if ($DryRun) { Write-Output "DRY RUN: $editorCli --install-extension $id"; continue }
        & $editorCli --install-extension $id
        if ($LASTEXITCODE -ne 0) { throw "Extension installation failed: $id" }
    }
}

function Wait-Readiness {
    if ($DryRun) { return }
    $deadline = (Get-Date).AddMinutes(4)
    do {
        try {
            $ready = Invoke-RestMethod -Uri 'http://localhost:8000/health/ready' -TimeoutSec 10
            if ($ready.success) { return }
        } catch { }
        Start-Sleep -Seconds 3
    } while ((Get-Date) -lt $deadline)
    throw 'API readiness timed out. Run Doctor and inspect docker compose logs backend.'
}

Push-Location $repo
try {
    if ($Action -eq 'InstallExtensions') { Install-EditorExtensions; exit 0 }
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Docker Desktop with Linux containers is required.' }
    switch ($Action) {
        'Setup' {
            if (-not (Test-Path '.env')) {
                if ($DryRun) { Write-Output 'DRY RUN: create .env from .env.example with a generated local JWT secret' }
                else {
                    $template = Get-Content '.env.example' -Raw
                    $secret = [Guid]::NewGuid().ToString('N') + [Guid]::NewGuid().ToString('N')
                    $template = $template -replace '(?m)^JWT_SECRET_KEY=.*$', "JWT_SECRET_KEY=$secret"
                    [IO.File]::WriteAllText((Join-Path $repo '.env'), $template, [Text.UTF8Encoding]::new($false))
                }
            }
            if (-not (Test-Path 'frontend/.env')) {
                if ($DryRun) { Write-Output 'DRY RUN: copy frontend/.env.example to frontend/.env' }
                else { Copy-Item 'frontend/.env.example' 'frontend/.env' }
            }
            Invoke-DockerChecked ($compose + @('config','--quiet'))
            Invoke-DockerChecked ($compose + @('build'))
            Invoke-DockerChecked ($compose + @('up','-d','--wait','postgres','redis','chromadb'))
            # Explicit population avoids Docker Desktop's nested bind/volume copy stall.
            Invoke-DockerChecked @('run','--rm','--mount','type=volume,source=dataanalyst_frontend_node_modules,target=/modules','--entrypoint','sh','dataanalyst-frontend','-c','cp -a /app/node_modules/. /modules/')
            Invoke-DockerChecked ($compose + @('run','--rm','--no-deps','frontend','npm','ci'))
            # Compose's one-shot migrate service initializes/upgrades the schema
            # before backend readiness can unblock the frontend.
            Invoke-DockerChecked ($compose + @('up','-d'))
            Wait-Readiness
            Install-EditorExtensions
        }
        'Doctor' {
            Invoke-DockerChecked @('version','--format','{{.Server.Version}}')
            Invoke-DockerChecked ($compose + @('config','--quiet'))
            Invoke-DockerChecked ($compose + @('ps'))
            # Pipe the current doctor to Python: no copying or file creation.
            Get-Content (Join-Path $PSScriptRoot 'environment_doctor.py') -Raw | & docker @compose exec -T -e PYTHONDONTWRITEBYTECODE=1 backend python -
            if ($LASTEXITCODE -ne 0) { throw 'Backend doctor failed.' }
            $nodeVersion = & docker @compose exec -T frontend node --version
            if ($LASTEXITCODE -ne 0 -or $nodeVersion -notmatch '^v22\.(\d+)\.' -or [int]$Matches[1] -lt 13) { throw 'Frontend requires Node >=22.13 and <23.' }
            Write-Output "Compatible Node: $nodeVersion"
            Invoke-DockerChecked ($compose + @('exec','-T','frontend','npm','ls','--depth=0'))
            $status = (Invoke-WebRequest -Uri 'http://localhost:5173' -UseBasicParsing -TimeoutSec 15).StatusCode
            if ($status -ne 200) { throw 'Frontend is unavailable.' }
            if (-not (Test-Path 'frontend/.env')) { throw 'frontend/.env missing: browser auth configuration required.' }
            $browserConfig = Get-Content 'frontend/.env' -Raw
            if ($browserConfig -notmatch '(?m)^VITE_SUPABASE_URL=https://(?!YOUR_PROJECT)[^\s]+' -or
                $browserConfig -notmatch '(?m)^VITE_SUPABASE_PUBLISHABLE_KEY=(?!YOUR_)[^\s]+') {
                throw 'Supabase browser configuration is missing or still a placeholder.'
            }
            Write-Output 'Frontend HTTP 200. Supabase values present (not a login verification).'
            Write-Output 'Worker startup registration (log evidence, not a live heartbeat):'
            $workerRegistration = & docker @compose logs --no-color backend | Select-String 'Durable background job worker launched' | Select-Object -Last 1
            if (-not $workerRegistration) { throw 'No durable worker startup registration found.' }
            Write-Output $workerRegistration
            Invoke-DockerChecked @('stats','--no-stream','--format','table {{.Name}}\t{{.MemUsage}}\t{{.CPUPerc}}')
        }
        'Start' {
            $startArgs = @('up','-d')
            if ($Build) { $startArgs += '--build' }
            Invoke-DockerChecked ($compose + $startArgs)
            Wait-Readiness
        }
        'Stop' { Invoke-DockerChecked ($toolsCompose + @('stop')) }
        'Infra' { Invoke-DockerChecked ($compose + @('up','-d','--wait','postgres','redis','chromadb')) }
        'Backend' { Invoke-DockerChecked ($compose + @('up','-d','backend')) }
        'Frontend' { Invoke-DockerChecked ($compose + @('up','-d','frontend')) }
        'Devtools' {
            Invoke-DockerChecked ($toolsCompose + @('build','devtools'))
            Invoke-DockerChecked ($toolsCompose + @('up','-d','--no-deps','devtools'))
        }
        'Debug' {
            Invoke-DockerChecked ($toolsCompose + @('up','-d','--no-deps','devtools'))
            Invoke-DockerChecked ($toolsCompose + @('exec','-T','devtools','python','-m','debugpy','--listen','0.0.0.0:5678','--wait-for-client','-m','uvicorn','backend.main:app','--host','0.0.0.0','--port','8001'))
        }
        'Browsers' {
            Invoke-DockerChecked ($toolsCompose + @('exec','-T','-w','/workspace/frontend','devtools','npx','playwright','install','--with-deps','chromium'))
        }
        'Lint' {
            Invoke-DockerChecked ($toolsCompose + @('run','--rm','--no-deps','devtools','ruff','check','backend','scripts'))
            Invoke-DockerChecked ($compose + @('exec','-T','frontend','npm','run','lint'))
            Invoke-DockerChecked ($compose + @('exec','-T','frontend','npx','tsc','-b','--pretty','false'))
        }
        'Test' {
            try {
                Invoke-DockerChecked ($verifyCompose + @('up','-d','postgres','redis','chromadb'))
                Invoke-DockerChecked ($verifyCompose + @('run','--rm','runner'))
                Invoke-DockerChecked ($verifyCompose + @('up','-d','api'))
                Invoke-DockerChecked ($verifyCompose + @('run','--rm','--no-deps','runner','python','scripts/verify_setup_journey.py'))
                Invoke-DockerChecked ($verifyCompose + @('restart','postgres','api'))
                Invoke-DockerChecked ($verifyCompose + @('run','--rm','--no-deps','runner','python','scripts/verify_setup_journey.py','--verify-persistence'))
            } finally {
                Invoke-DockerChecked ($verifyCompose + @('stop'))
            }
        }
    }
    exit 0
} catch {
    Write-Error $_ -ErrorAction Continue
    exit 1
} finally {
    Pop-Location
}
