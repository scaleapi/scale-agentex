# AgentEx PowerShell Build Script
# Provides automation for development workflows on Windows

param(
    [Parameter(Position=0)]
    [string]$Command = "help",
    
    [Parameter(Position=1)]
    [string]$Name = "",
    
    [Parameter(Position=2)]
    [string]$File = "",
    
    [string]$Args = "",
    
    [string]$Tag = "latest",
    [string]$ImageName = "agentex",
    [string]$Platform = "linux/amd64",
    [string]$Registry = ""
)

function Show-Help {
    Write-Host "AgentEx Development Commands:" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Development Commands:" -ForegroundColor Yellow
    Write-Host "  install              Install dependencies" -ForegroundColor Green
    Write-Host "  install-dev          Install dependencies including dev group" -ForegroundColor Green
    Write-Host "  install-docs         Install docs dependencies" -ForegroundColor Green
    Write-Host "  clean                Clean virtual environment and lock file" -ForegroundColor Green
    Write-Host "  env                  Show how to activate virtual environment" -ForegroundColor Green
    Write-Host ""
    Write-Host "Development Server:" -ForegroundColor Yellow
    Write-Host "  dev                  Start development server with Docker Compose" -ForegroundColor Green
    Write-Host "  dev-stop             Stop development server" -ForegroundColor Green
    Write-Host "  dev-wipe             Stop dev server and wipe DB" -ForegroundColor Green
    Write-Host ""
    Write-Host "Database Commands:" -ForegroundColor Yellow
    Write-Host "  migration            Create a new migration (usage: .\build.ps1 migration -Name 'migration_name')" -ForegroundColor Green
    Write-Host "  apply-migrations     Apply database migrations" -ForegroundColor Green
    Write-Host ""
    Write-Host "Documentation:" -ForegroundColor Yellow
    Write-Host "  serve-docs           Serve documentation locally" -ForegroundColor Green
    Write-Host "  build-docs           Build documentation" -ForegroundColor Green
    Write-Host ""
    Write-Host "Docker:" -ForegroundColor Yellow
    Write-Host "  docker-build         Build production Docker image" -ForegroundColor Green
    Write-Host "  docker-build-with-docs  Build production Docker image with docs" -ForegroundColor Green
    Write-Host ""
    Write-Host "Test Commands:" -ForegroundColor Yellow
    Write-Host "  test                 Run tests" -ForegroundColor Green
    Write-Host "  test-unit            Run unit tests only" -ForegroundColor Green
    Write-Host "  test-integration     Run integration tests only" -ForegroundColor Green
    Write-Host "  test-cov             Run tests with coverage report" -ForegroundColor Green
    Write-Host "  test-docker-check    Check Docker environment setup for testing" -ForegroundColor Green
    Write-Host "  test-help            Show test command examples" -ForegroundColor Green
    Write-Host ""
    Write-Host "Usage: .\build.ps1 <command> [options]" -ForegroundColor Cyan
}

function Invoke-Install {
    Write-Host "🚀 Installing dependencies..." -ForegroundColor Cyan
    uv sync
    if ($LASTEXITCODE -ne 0) { exit 1 }
    
    Push-Location ..
    uv run pre-commit install
    Pop-Location
    
    Write-Host "Installation complete!" -ForegroundColor Green
}

function Invoke-InstallDev {
    Write-Host "🚀 Installing dependencies with dev group..." -ForegroundColor Cyan
    
    # Check if parent repo-setup is needed
    if (-not (Test-Path "../.venv")) {
        Write-Host "Running repo-setup..." -ForegroundColor Yellow
        Push-Location ..
        & ".\build.ps1" repo-setup
        Pop-Location
    }
    
    uv sync --group dev
    if ($LASTEXITCODE -ne 0) { exit 1 }
    
    Write-Host "Dev installation complete!" -ForegroundColor Green
}

function Invoke-InstallDocs {
    Write-Host "🚀 Installing docs dependencies..." -ForegroundColor Cyan
    uv sync --group docs
    if ($LASTEXITCODE -ne 0) { exit 1 }
    Write-Host "Docs dependencies installed!" -ForegroundColor Green
}

function Invoke-Clean {
    Write-Host "🧹 Cleaning virtual environment..." -ForegroundColor Cyan
    if (Test-Path ".venv") {
        Remove-Item -Recurse -Force .venv
        Write-Host "Removed .venv directory" -ForegroundColor Yellow
    }
    if (Test-Path "uv.lock") {
        Remove-Item -Force uv.lock
        Write-Host "Removed uv.lock file" -ForegroundColor Yellow
    }
    Write-Host "Clean complete!" -ForegroundColor Green
}

function Show-EnvActivation {
    Write-Host "To activate the virtual environment, use:" -ForegroundColor Cyan
    Write-Host "  .venv\Scripts\Activate.ps1" -ForegroundColor Green
    Write-Host ""
    Write-Host "Or in Command Prompt:" -ForegroundColor Cyan
    Write-Host "  .venv\Scripts\activate.bat" -ForegroundColor Green
}

function Invoke-Dev {
    Write-Host "🚀 Starting development server with Docker Compose..." -ForegroundColor Cyan
    Invoke-InstallDev
    docker compose up --build
}

function Invoke-DevStop {
    Write-Host "Stopping dev server..." -ForegroundColor Cyan
    docker compose down
    Write-Host "Dev server stopped!" -ForegroundColor Green
}

function Invoke-DevWipe {
    Write-Host "Stopping dev server and wiping DB..." -ForegroundColor Cyan
    docker compose down -v
    Write-Host "Dev server stopped and DB wiped!" -ForegroundColor Green
}

function Invoke-Migration {
    if ([string]::IsNullOrWhiteSpace($Name)) {
        Write-Host "❌ Error: NAME is required" -ForegroundColor Red
        Write-Host "Usage: .\build.ps1 migration -Name 'migration_name'" -ForegroundColor Yellow
        exit 1
    }
    
    Write-Host "Creating migration: $Name" -ForegroundColor Cyan
    Push-Location database\migrations
    alembic revision --autogenerate -m $Name
    if ($LASTEXITCODE -eq 0) {
        alembic history | Out-File -FilePath migration_history.txt -Encoding utf8
        Write-Host "Migration created successfully!" -ForegroundColor Green
    } else {
        Write-Host "Failed to create migration" -ForegroundColor Red
    }
    Pop-Location
}

function Invoke-ApplyMigrations {
    Write-Host "Applying database migrations..." -ForegroundColor Cyan
    Push-Location database\migrations
    alembic upgrade head
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Migrations applied successfully!" -ForegroundColor Green
    } else {
        Write-Host "Failed to apply migrations" -ForegroundColor Red
    }
    Pop-Location
}

function Invoke-ServeDocs {
    Write-Host "📚 Installing docs dependencies..." -ForegroundColor Cyan
    uv sync --group docs
    if ($LASTEXITCODE -ne 0) { exit 1 }
    
    Write-Host "Starting docs server..." -ForegroundColor Cyan
    Push-Location docs
    uv run mkdocs serve -a localhost:8001
    Pop-Location
}

function Invoke-BuildDocs {
    Write-Host "📚 Building documentation..." -ForegroundColor Cyan
    uv sync --group docs
    if ($LASTEXITCODE -ne 0) { exit 1 }
    
    Push-Location docs
    uv run mkdocs build
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Documentation built successfully!" -ForegroundColor Green
    }
    Pop-Location
}

function Invoke-DockerBuild {
    Write-Host "🐳 Building production Docker image..." -ForegroundColor Cyan
    docker buildx build --platform=$Platform --load -f Dockerfile --target production -t ${ImageName}:${Tag} ../
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Docker image built successfully!" -ForegroundColor Green
    }
}

function Invoke-DockerBuildWithDocs {
    Write-Host "🐳 Building production Docker image with docs..." -ForegroundColor Cyan
    docker buildx build --platform=$Platform --load -f Dockerfile --target production -t ${ImageName}:${Tag} --build-arg INCLUDE_DOCS=true .
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Docker image with docs built successfully!" -ForegroundColor Green
    }
}

function Invoke-Test {
    $testArgs = @()
    
    if (-not [string]::IsNullOrWhiteSpace($File)) {
        $testArgs += $File
    }
    
    if (-not [string]::IsNullOrWhiteSpace($Name)) {
        $testArgs += "-k"
        $testArgs += $Name
    }
    
    if (-not [string]::IsNullOrWhiteSpace($Args)) {
        $testArgs += "--pytest-args"
        $testArgs += $Args
    }
    
    Write-Host "Running tests..." -ForegroundColor Cyan
    uv run python scripts/run_tests.py @testArgs
}

function Invoke-TestUnit {
    Write-Host "Running unit tests..." -ForegroundColor Cyan
    uv run python scripts/run_tests.py -m unit
}

function Invoke-TestIntegration {
    Write-Host "Running integration tests..." -ForegroundColor Cyan
    uv run python scripts/run_tests.py -m integration
}

function Invoke-TestCov {
    Write-Host "Running tests with coverage..." -ForegroundColor Cyan
    uv run python scripts/run_tests.py --cov=src --cov-report=html --cov-report=term
}

function Invoke-TestDockerCheck {
    Write-Host "Checking Docker environment..." -ForegroundColor Cyan
    uv run python scripts/test_setup.py --check-docker
}

function Show-TestHelp {
    Write-Host "Test Command Examples:" -ForegroundColor Cyan
    Write-Host "  .\build.ps1 test                                       # Run all tests" -ForegroundColor Green
    Write-Host "  .\build.ps1 test -File tests/unit/                     # Run all unit tests" -ForegroundColor Green
    Write-Host "  .\build.ps1 test -File tests/unit/test_foo.py          # Run specific file" -ForegroundColor Green
    Write-Host "  .\build.ps1 test -Name crud                            # Run tests matching 'crud'" -ForegroundColor Green
    Write-Host "  .\build.ps1 test -Name 'test_create or test_update'    # Multiple patterns" -ForegroundColor Green
    Write-Host "  .\build.ps1 test -Args '-v -s'                         # Pass pytest arguments" -ForegroundColor Green
    Write-Host "  .\build.ps1 test-unit                                  # Shortcut for unit tests" -ForegroundColor Green
    Write-Host "  .\build.ps1 test-integration                           # Shortcut for integration tests" -ForegroundColor Green
    Write-Host "  .\build.ps1 test-cov                                   # Run with coverage report" -ForegroundColor Green
    Write-Host "  .\build.ps1 test-docker-check                          # Check Docker setup" -ForegroundColor Green
}

# Main command dispatcher
switch ($Command.ToLower()) {
    "help" { Show-Help }
    "install" { Invoke-Install }
    "install-dev" { Invoke-InstallDev }
    "install-docs" { Invoke-InstallDocs }
    "clean" { Invoke-Clean }
    "env" { Show-EnvActivation }
    "dev" { Invoke-Dev }
    "dev-stop" { Invoke-DevStop }
    "dev-wipe" { Invoke-DevWipe }
    "migration" { Invoke-Migration }
    "apply-migrations" { Invoke-ApplyMigrations }
    "serve-docs" { Invoke-ServeDocs }
    "build-docs" { Invoke-BuildDocs }
    "docker-build" { Invoke-DockerBuild }
    "docker-build-with-docs" { Invoke-DockerBuildWithDocs }
    "test" { Invoke-Test }
    "test-unit" { Invoke-TestUnit }
    "test-integration" { Invoke-TestIntegration }
    "test-cov" { Invoke-TestCov }
    "test-docker-check" { Invoke-TestDockerCheck }
    "test-help" { Show-TestHelp }
    default {
        Write-Host "Unknown command: $Command" -ForegroundColor Red
        Write-Host ""
        Show-Help
        exit 1
    }
}

