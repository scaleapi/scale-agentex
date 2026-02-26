# AgentEx Workspace PowerShell Script
# This script provides the same functionality as the Makefile for Windows users

param(
    [Parameter(Position=0)]
    [string]$Command = "help"
)

function Show-Help {
    Write-Host "AgentEx Workspace Commands:" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  repo-setup       Setup development environment for the workspace" -ForegroundColor Green
    Write-Host "  help             Show this help message" -ForegroundColor Green
    Write-Host ""
    Write-Host "Usage: .\build.ps1 <command>" -ForegroundColor Yellow
    Write-Host "Example: .\build.ps1 repo-setup" -ForegroundColor Yellow
}

function Invoke-RepoSetup {
    Write-Host "Setting up development environment..." -ForegroundColor Cyan
    
    # Run uv sync with dev group
    Write-Host "Installing dependencies with uv..." -ForegroundColor Yellow
    uv sync --group dev
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Error: Failed to sync dependencies" -ForegroundColor Red
        exit 1
    }
    
    # Install pre-commit hooks
    Write-Host "Installing pre-commit hooks..." -ForegroundColor Yellow
    uv run pre-commit install
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Error: Failed to install pre-commit hooks" -ForegroundColor Red
        exit 1
    }
    
    Write-Host "Repository setup complete!" -ForegroundColor Green
}

# Main command dispatcher
switch ($Command.ToLower()) {
    "repo-setup" {
        Invoke-RepoSetup
    }
    "help" {
        Show-Help
    }
    default {
        Write-Host "Unknown command: $Command" -ForegroundColor Red
        Write-Host ""
        Show-Help
        exit 1
    }
}

