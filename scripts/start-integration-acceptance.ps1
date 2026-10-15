# Additive, isolated acceptance infrastructure. Never mounts customer storage.
# Uses the existing application image/source and existing Supabase configuration.
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$prefix = 'integration-acceptance'
function DockerChecked {
    & docker @args
    if ($LASTEXITCODE -ne 0) { throw 'Acceptance Docker command failed' }
}
if (& docker ps -a --filter "name=$prefix" --format '{{.Names}}') {
    throw 'Acceptance containers already exist. Inspect their state before restarting this script.'
}
DockerChecked network create "$prefix-network"
DockerChecked run -d --name "$prefix-postgres" --network "$prefix-network" -e POSTGRES_DB=acceptance -e POSTGRES_USER=acceptance -e POSTGRES_PASSWORD=isolated-development-only postgres:16
DockerChecked run -d --name "$prefix-redis" --network "$prefix-network" redis:7
# Match the installed client exactly. The unpinned Chroma 1.0 server rejects
# collection parsing by the application's 0.6.3 client (missing _type).
DockerChecked run -d --name "$prefix-chroma063" --network "$prefix-network" --mount "type=volume,source=$prefix-chroma063-storage,target=/chroma,volume-nocopy" ai-data-analyst-os-backend chroma run --host 0.0.0.0 --port 8000 --path /chroma
$backendArgs = @('run', '-d', '--name', "$prefix-backend", '--network', "$prefix-network",
    '-p', '127.0.0.1:8011:8000', '--env-file', (Join-Path $repo '.env'),
    '-e', 'DATABASE_URL=postgresql+psycopg://acceptance:isolated-development-only@integration-acceptance-postgres:5432/acceptance',
    '-e', 'REDIS_URL=redis://integration-acceptance-redis:6379/0', '-e', 'REDIS_PASSWORD=',
    '-e', 'REDIS_HOST=integration-acceptance-redis', '-e', 'CHROMA_HOST=integration-acceptance-chroma063',
    '-e', 'CHROMA_PORT=8000', '-e', 'ENVIRONMENT=development', '-e', 'DEBUG=false',
    '-e', 'FRONTEND_URL=http://localhost:5174', '-e', 'CORS_ORIGINS=http://localhost:5174',
    '-e', 'UPLOAD_DIR=storage',
    '--mount', "type=bind,source=$repo\backend,target=/app/backend,readonly",
    '--mount', "type=bind,source=$repo\migrations,target=/app/migrations,readonly",
    '--mount', "type=bind,source=$repo\alembic.ini,target=/app/alembic.ini,readonly",
    '--mount', "type=bind,source=$repo\tests,target=/app/tests,readonly",
    '--mount', "type=volume,source=$prefix-storage,target=/app/storage,volume-nocopy",
    'ai-data-analyst-os-backend', 'sleep', 'infinity')
DockerChecked @backendArgs
Write-Output 'Isolated containers created. Apply migrations before starting the acceptance API.'
