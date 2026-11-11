param([Parameter(Mandatory=$true)][string]$Finding)
$ErrorActionPreference='Continue'
$evidence="docs/integration-repairs/20261109/$Finding"
$retiredProjects=@('dataanalyst-dataplane-audit','dataanalyst-quality','dataanalyst-perceptron-phase8','dataanalyst-perceptron-phase1')
$retiredContainers=@(foreach ($retiredProject in $retiredProjects) { docker ps -q --filter "label=com.docker.compose.project=$retiredProject" })
if ($retiredContainers.Count -gt 0) {
    docker stop @retiredContainers *> "$evidence-retired-stacks.log"
    if ($LASTEXITCODE -ne 0) { Write-Output "$Finding RETIRED STACK ISOLATION FAILED"; exit 1 }
}
docker compose -p dataanalyst-integration-audit -f docker-compose.verify.yml -f docker-compose.learning-verify.yml -f docker-compose.dataplane-browser.yml -f docs/integration-audit/20261108/compose-audit.yml stop api dataplane-worker frontend-verify *> "$evidence-isolation.log"
if ($LASTEXITCODE -ne 0) { Write-Output "$Finding ISOLATION FAILED"; exit 1 }
docker compose -p dataanalyst-integration-audit -f docker-compose.verify.yml -f docs/integration-repairs/20261109/compose.yml run --rm --no-deps runner python scripts/run_setup_tests.py backend/tests tests "--junitxml=/verification/$Finding-full.xml" *> "$evidence-backend.log"
if ($LASTEXITCODE -ne 0) { Write-Output "$Finding BACKEND FAILED"; exit 1 }
docker exec dataanalyst-frontend-1 sh -c 'npm run typecheck && npm run build' *> "$evidence-frontend.log"
if ($LASTEXITCODE -ne 0) { Write-Output "$Finding FRONTEND FAILED"; exit 1 }
docker cp "dataanalyst-integration-audit-api-1:/verification/$Finding-full.xml" "$evidence-full.xml"
if ($LASTEXITCODE -ne 0) { Write-Output "$Finding EVIDENCE COPY FAILED"; exit 1 }
Write-Output "$Finding ALL REQUIRED CHECKS PASSED"
