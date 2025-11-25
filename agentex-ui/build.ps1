# AgentEx UI PowerShell Build Script
# Provides Docker build automation for Windows users

param(
    [Parameter(Position=0)]
    [string]$Command = "help",
    
    [string]$ImageName = "agentex-ui",
    [string]$Tag = "latest",
    [string]$Platform = "linux/amd64",
    [string]$Registry = ""
)

# Calculate full image name
$FullImageName = if ($Registry) { "$Registry/$ImageName" } else { $ImageName }

function Show-Help {
    Write-Host "Available targets:" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Setup:" -ForegroundColor Yellow
    Write-Host "  setup-buildx         Set up Docker buildx builder (run once)" -ForegroundColor Green
    Write-Host ""
    Write-Host "Build Commands:" -ForegroundColor Yellow
    Write-Host "  build                Build Docker image for linux/amd64 platform" -ForegroundColor Green
    Write-Host "  build-no-cache       Build Docker image without cache" -ForegroundColor Green
    Write-Host "  build-debug          Build Docker image with verbose output for debugging" -ForegroundColor Green
    Write-Host "  build-and-load       Build Docker image and load it to local Docker daemon" -ForegroundColor Green
    Write-Host ""
    Write-Host "Run Commands:" -ForegroundColor Yellow
    Write-Host "  run                  Run the Docker container locally" -ForegroundColor Green
    Write-Host "  run-detached         Run the Docker container in detached mode" -ForegroundColor Green
    Write-Host "  stop                 Stop the running container" -ForegroundColor Green
    Write-Host ""
    Write-Host "Registry Commands:" -ForegroundColor Yellow
    Write-Host "  push                 Push the image to registry (requires -Registry)" -ForegroundColor Green
    Write-Host "  build-and-push       Build and push Docker image directly (requires -Registry)" -ForegroundColor Green
    Write-Host ""
    Write-Host "Utility Commands:" -ForegroundColor Yellow
    Write-Host "  clean                Remove the Docker image" -ForegroundColor Green
    Write-Host "  inspect              Inspect the Docker image" -ForegroundColor Green
    Write-Host "  logs                 Show logs from running container" -ForegroundColor Green
    Write-Host "  shell                Open shell in running container" -ForegroundColor Green
    Write-Host ""
    Write-Host "Development Commands:" -ForegroundColor Yellow
    Write-Host "  dev                  Run development server locally (without Docker)" -ForegroundColor Green
    Write-Host "  install              Install dependencies" -ForegroundColor Green
    Write-Host "  typecheck            Run TypeScript type checking" -ForegroundColor Green
    Write-Host "  lint                 Run linting" -ForegroundColor Green
    Write-Host ""
    Write-Host "Quick Commands:" -ForegroundColor Yellow
    Write-Host "  build-and-run        Build and run the container" -ForegroundColor Green
    Write-Host "  build-and-run-detached  Build and run the container in detached mode" -ForegroundColor Green
    Write-Host ""
    Write-Host "Usage: .\build.ps1 <command> [options]" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Examples:" -ForegroundColor Yellow
    Write-Host "  .\build.ps1 build -Tag v1.0.0 -Registry myregistry.com" -ForegroundColor Green
    Write-Host "  .\build.ps1 push -Tag v1.0.0 -Registry myregistry.com" -ForegroundColor Green
    Write-Host "  .\build.ps1 build -ImageName my-custom-name -Tag latest" -ForegroundColor Green
}

function Invoke-SetupBuildx {
    Write-Host "Setting up Docker buildx builder..." -ForegroundColor Cyan
    
    # Check if builder exists
    $builderExists = docker buildx inspect agentex-builder 2>$null
    
    if (-not $builderExists) {
        Write-Host "Creating new buildx builder..." -ForegroundColor Yellow
        docker buildx create --name agentex-builder --driver docker-container --bootstrap
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Failed to create buildx builder" -ForegroundColor Red
            exit 1
        }
    }
    
    docker buildx use agentex-builder
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ Docker buildx builder 'agentex-builder' is ready" -ForegroundColor Green
    } else {
        Write-Host "Failed to use buildx builder" -ForegroundColor Red
        exit 1
    }
}

function Invoke-Typecheck {
    Write-Host "Running TypeScript type checking..." -ForegroundColor Cyan
    npm run typecheck
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Type checking failed" -ForegroundColor Red
        exit 1
    }
}

function Invoke-Lint {
    Write-Host "Running linting..." -ForegroundColor Cyan
    npm run lint
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Linting failed" -ForegroundColor Red
        exit 1
    }
}

function Invoke-Build {
    Write-Host "Building ${FullImageName}:${Tag} for platform ${Platform}..." -ForegroundColor Cyan
    Invoke-Typecheck
    Invoke-Lint
    
    docker buildx build --platform $Platform -t "${FullImageName}:${Tag}" .
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ Build complete: ${FullImageName}:${Tag}" -ForegroundColor Green
    } else {
        Write-Host "Build failed" -ForegroundColor Red
        exit 1
    }
}

function Invoke-BuildNoCache {
    Write-Host "Building ${FullImageName}:${Tag} for platform ${Platform} (no cache)..." -ForegroundColor Cyan
    Invoke-Typecheck
    Invoke-Lint
    
    docker buildx build --platform $Platform --no-cache -t "${FullImageName}:${Tag}" .
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ Build complete: ${FullImageName}:${Tag}" -ForegroundColor Green
    } else {
        Write-Host "Build failed" -ForegroundColor Red
        exit 1
    }
}

function Invoke-BuildDebug {
    Write-Host "Building ${FullImageName}:${Tag} for platform ${Platform} (debug mode)..." -ForegroundColor Cyan
    Invoke-Typecheck
    Invoke-Lint
    
    docker buildx build --platform $Platform --progress=plain --no-cache -t "${FullImageName}:${Tag}" .
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ Build complete: ${FullImageName}:${Tag}" -ForegroundColor Green
    } else {
        Write-Host "Build failed" -ForegroundColor Red
        exit 1
    }
}

function Invoke-BuildAndLoad {
    Write-Host "Building and loading ${FullImageName}:${Tag} for platform ${Platform}..." -ForegroundColor Cyan
    Invoke-Typecheck
    Invoke-Lint
    
    docker buildx build --platform $Platform --load -t "${FullImageName}:${Tag}" .
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ Build complete and loaded: ${FullImageName}:${Tag}" -ForegroundColor Green
    } else {
        Write-Host "Build and load failed" -ForegroundColor Red
        exit 1
    }
}

function Invoke-Run {
    Write-Host "Running ${FullImageName}:${Tag}..." -ForegroundColor Cyan
    docker run --rm -p 3000:3000 --platform $Platform "${FullImageName}:${Tag}"
}

function Invoke-RunDetached {
    Write-Host "Running ${FullImageName}:${Tag} in detached mode..." -ForegroundColor Cyan
    docker run -d --name agentex-ui -p 3000:3000 --platform $Platform "${FullImageName}:${Tag}"
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ Container started. Access at http://localhost:3000" -ForegroundColor Green
    } else {
        Write-Host "Failed to start container" -ForegroundColor Red
        exit 1
    }
}

function Invoke-Stop {
    Write-Host "Stopping agentex-ui container..." -ForegroundColor Cyan
    docker stop agentex-ui 2>$null
    docker rm agentex-ui 2>$null
    Write-Host "✅ Container stopped and removed" -ForegroundColor Green
}

function Invoke-Push {
    if ([string]::IsNullOrWhiteSpace($Registry)) {
        Write-Host "❌ Error: REGISTRY must be set to push image" -ForegroundColor Red
        Write-Host "Usage: .\build.ps1 push -Registry your-registry.com" -ForegroundColor Yellow
        exit 1
    }
    
    Write-Host "Pushing ${FullImageName}:${Tag}..." -ForegroundColor Cyan
    docker push "${FullImageName}:${Tag}"
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ Push complete: ${FullImageName}:${Tag}" -ForegroundColor Green
    } else {
        Write-Host "Push failed" -ForegroundColor Red
        exit 1
    }
}

function Invoke-BuildAndPush {
    if ([string]::IsNullOrWhiteSpace($Registry)) {
        Write-Host "❌ Error: REGISTRY must be set to build and push image" -ForegroundColor Red
        Write-Host "Usage: .\build.ps1 build-and-push -Registry your-registry.com" -ForegroundColor Yellow
        exit 1
    }
    
    Write-Host "Building and pushing ${FullImageName}:${Tag} for platform ${Platform}..." -ForegroundColor Cyan
    Invoke-Typecheck
    Invoke-Lint
    
    docker buildx build --platform $Platform --push -t "${FullImageName}:${Tag}" .
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ Build and push complete: ${FullImageName}:${Tag}" -ForegroundColor Green
    } else {
        Write-Host "Build and push failed" -ForegroundColor Red
        exit 1
    }
}

function Invoke-Clean {
    Write-Host "Removing ${FullImageName}:${Tag}..." -ForegroundColor Cyan
    docker rmi "${FullImageName}:${Tag}" 2>$null
    Write-Host "✅ Image removed" -ForegroundColor Green
}

function Invoke-Inspect {
    Write-Host "Inspecting ${FullImageName}:${Tag}..." -ForegroundColor Cyan
    docker inspect "${FullImageName}:${Tag}"
}

function Invoke-Logs {
    Write-Host "Showing logs from agentex-ui container..." -ForegroundColor Cyan
    docker logs -f agentex-ui
}

function Invoke-Shell {
    Write-Host "Opening shell in agentex-ui container..." -ForegroundColor Cyan
    docker exec -it agentex-ui /bin/sh
}

function Invoke-Dev {
    Write-Host "Starting development server..." -ForegroundColor Cyan
    Invoke-Install
    npm run dev
}

function Invoke-Install {
    Write-Host "Installing dependencies..." -ForegroundColor Cyan
    npm install
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ Dependencies installed" -ForegroundColor Green
    } else {
        Write-Host "Installation failed" -ForegroundColor Red
        exit 1
    }
}

function Invoke-BuildAndRun {
    Invoke-BuildAndLoad
    Invoke-Run
}

function Invoke-BuildAndRunDetached {
    Invoke-BuildAndLoad
    Invoke-RunDetached
}

# Main command dispatcher
switch ($Command.ToLower()) {
    "help" { Show-Help }
    "setup-buildx" { Invoke-SetupBuildx }
    "build" { Invoke-Build }
    "build-no-cache" { Invoke-BuildNoCache }
    "build-debug" { Invoke-BuildDebug }
    "build-and-load" { Invoke-BuildAndLoad }
    "run" { Invoke-Run }
    "run-detached" { Invoke-RunDetached }
    "stop" { Invoke-Stop }
    "push" { Invoke-Push }
    "build-and-push" { Invoke-BuildAndPush }
    "clean" { Invoke-Clean }
    "inspect" { Invoke-Inspect }
    "logs" { Invoke-Logs }
    "shell" { Invoke-Shell }
    "dev" { Invoke-Dev }
    "install" { Invoke-Install }
    "typecheck" { Invoke-Typecheck }
    "lint" { Invoke-Lint }
    "build-and-run" { Invoke-BuildAndRun }
    "build-and-run-detached" { Invoke-BuildAndRunDetached }
    default {
        Write-Host "Unknown command: $Command" -ForegroundColor Red
        Write-Host ""
        Show-Help
        exit 1
    }
}

