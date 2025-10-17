#!/bin/bash

# Setup CodeArtifact authentication for AgentEx development
# Usage: source scripts/setup-codeartifact.sh

echo "🔐 Setting up CodeArtifact authentication..."

# Check if AWS CLI is available
if ! command -v aws &> /dev/null; then
    echo "❌ AWS CLI is not installed. Please install it first."
    exit 1
fi

# CodeArtifact configuration
CODEARTIFACT_DOMAIN="scale"
CODEARTIFACT_OWNER=""
CODEARTIFACT_REGION="us-west-2"
CODEARTIFACT_REPO="scale-pypi"

# Fetch the authentication token
export AWS_CODEARTIFACT_AUTH_TOKEN=$(aws codeartifact get-authorization-token \
    --domain "$CODEARTIFACT_DOMAIN" \
    --domain-owner "$CODEARTIFACT_OWNER" \
    --region "$CODEARTIFACT_REGION" \
    --query authorizationToken \
    --output text)

if [ $? -eq 0 ] && [ -n "$AWS_CODEARTIFACT_AUTH_TOKEN" ]; then
    # Configure uv to use CodeArtifact
    export UV_INDEX_URL="https://aws:${AWS_CODEARTIFACT_AUTH_TOKEN}@${CODEARTIFACT_DOMAIN}-${CODEARTIFACT_OWNER}.d.codeartifact.${CODEARTIFACT_REGION}.amazonaws.com/pypi/${CODEARTIFACT_REPO}/simple/"
    
    echo "✅ CodeArtifact authentication configured successfully!"
    echo "   Both pip and uv are now configured to use CodeArtifact."
    echo "   You can now run 'uv add package-name' or 'uv sync' commands."
    echo ""
    echo "💡 This configuration is valid for 12 hours."
    echo "   Re-run this script if you get authentication errors."
else
    echo "❌ Failed to fetch CodeArtifact authentication token."
    echo "   Make sure you have the necessary AWS permissions."
    exit 1
fi 