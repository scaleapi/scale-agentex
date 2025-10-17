#!/bin/bash

# Setup CodeArtifact pip.conf for Docker builds
# Usage: ./setup-build-codeartifact.sh

echo "🔐 Setting up CodeArtifact pip.conf for Docker builds..."

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
echo "🔑 Fetching CodeArtifact authentication token..."
TOKEN=$(aws codeartifact get-authorization-token \
    --domain "$CODEARTIFACT_DOMAIN" \
    --domain-owner "$CODEARTIFACT_OWNER" \
    --region "$CODEARTIFACT_REGION" \
    --query authorizationToken \
    --output text 2>/dev/null)

if [ $? -eq 0 ] && [ -n "$TOKEN" ]; then
    echo "✅ Successfully obtained CodeArtifact token"
    
    # Generate the pip.conf file for Docker builds
    cat > .codeartifact-pip-conf << EOF
[global]
index-url = https://aws:${TOKEN}@${CODEARTIFACT_DOMAIN}-${CODEARTIFACT_OWNER}.d.codeartifact.${CODEARTIFACT_REGION}.amazonaws.com/pypi/${CODEARTIFACT_REPO}/simple/

EOF

    echo "✅ Generated .codeartifact-pip-conf file for Docker builds"
    echo ""
    echo "💡 This file is valid for 12 hours."
    echo "   Re-run this script if you get authentication errors."
    echo ""
    echo "🐳 You can now build with CodeArtifact access:"
    echo "   agentex agents build --manifest manifest.yaml --secret 'id=codeartifact-pip-conf,src=.codeartifact-pip-conf'"
    
else
    echo "❌ Failed to fetch CodeArtifact authentication token."
    echo "   Make sure you have the necessary AWS permissions."
    exit 1
fi 