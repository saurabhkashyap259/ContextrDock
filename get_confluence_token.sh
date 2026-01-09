#!/bin/bash
# Helper script to get Confluence OAuth token
# This script guides you through the OAuth 2.0 authorization code flow

set -e

echo "================================================"
echo "Confluence OAuth Token Generator"
echo "================================================"
echo ""

# Check if we have credentials
if [ -z "$CONFLUENCE_CLIENT_ID" ] || [ -z "$CONFLUENCE_CLIENT_SECRET" ]; then
    echo "⚠️  OAuth credentials not found in environment"
    echo ""
    echo "You need to create an OAuth app first:"
    echo "1. Go to: https://developer.atlassian.com/console/myapps/"
    echo "2. Create OAuth 2.0 integration"
    echo "3. Add scopes: read:confluence-content.all, read:confluence-space.summary"
    echo "4. Add callback URL: http://localhost:8080/callback"
    echo ""
    read -p "Enter your CLIENT_ID: " CLIENT_ID
    read -p "Enter your CLIENT_SECRET: " CLIENT_SECRET
    echo ""
else
    CLIENT_ID="$CONFLUENCE_CLIENT_ID"
    CLIENT_SECRET="$CONFLUENCE_CLIENT_SECRET"
    echo "✅ Using credentials from environment"
fi

# Set redirect URI
REDIRECT_URI="http://localhost:8080/callback"

# Generate authorization URL
AUTH_URL="https://auth.atlassian.com/authorize?audience=api.atlassian.com&client_id=${CLIENT_ID}&scope=read:confluence-content.all%20read:confluence-space.summary&redirect_uri=${REDIRECT_URI}&response_type=code&prompt=consent"

echo "================================================"
echo "STEP 1: Authorize the app"
echo "================================================"
echo ""
echo "Opening browser to authorize..."
echo ""

# Open browser (works on macOS, Linux, and WSL)
if command -v open &> /dev/null; then
    open "$AUTH_URL"
elif command -v xdg-open &> /dev/null; then
    xdg-open "$AUTH_URL"
else
    echo "Please open this URL in your browser:"
    echo "$AUTH_URL"
fi

echo ""
echo "After authorizing, you'll be redirected to:"
echo "http://localhost:8080/callback?code=YOUR_CODE"
echo ""
echo "The page may show an error (that's normal - we just need the code!)"
echo ""

read -p "Paste the ENTIRE callback URL here: " CALLBACK_URL

# Extract code from URL
AUTH_CODE=$(echo "$CALLBACK_URL" | grep -oP '(?<=code=)[^&]+' || echo "$CALLBACK_URL" | sed -n 's/.*code=\([^&]*\).*/\1/p')

if [ -z "$AUTH_CODE" ]; then
    echo ""
    echo "❌ Could not extract authorization code from URL"
    echo "Make sure you pasted the full URL including ?code=..."
    exit 1
fi

echo ""
echo "✅ Authorization code extracted: ${AUTH_CODE:0:20}..."
echo ""

echo "================================================"
echo "STEP 2: Exchange code for access token"
echo "================================================"
echo ""

# Exchange code for token
RESPONSE=$(curl -s -X POST https://auth.atlassian.com/oauth/token \
  -H "Content-Type: application/json" \
  -d '{
    "grant_type": "authorization_code",
    "client_id": "'"$CLIENT_ID"'",
    "client_secret": "'"$CLIENT_SECRET"'",
    "code": "'"$AUTH_CODE"'",
    "redirect_uri": "'"$REDIRECT_URI"'"
  }')

# Check for errors
if echo "$RESPONSE" | grep -q '"error"'; then
    echo "❌ Error getting access token:"
    echo "$RESPONSE" | python -m json.tool 2>/dev/null || echo "$RESPONSE"
    echo ""
    echo "Common issues:"
    echo "- Authorization code already used (get a new one)"
    echo "- Code expired (they expire after 10 minutes)"
    echo "- Redirect URI mismatch"
    echo ""
    echo "💡 TIP: Use API Token instead - it's much easier!"
    echo "   Go to: https://id.atlassian.com/manage-profile/security/api-tokens"
    exit 1
fi

# Extract access token
ACCESS_TOKEN=$(echo "$RESPONSE" | python -c "import sys, json; print(json.load(sys.stdin)['access_token'])" 2>/dev/null)
REFRESH_TOKEN=$(echo "$RESPONSE" | python -c "import sys, json; print(json.load(sys.stdin).get('refresh_token', 'N/A'))" 2>/dev/null)
EXPIRES_IN=$(echo "$RESPONSE" | python -c "import sys, json; print(json.load(sys.stdin).get('expires_in', 'N/A'))" 2>/dev/null)

if [ -z "$ACCESS_TOKEN" ]; then
    echo "❌ Could not parse access token from response"
    echo "$RESPONSE"
    exit 1
fi

echo "✅ Access token obtained successfully!"
echo ""
echo "================================================"
echo "Token Details"
echo "================================================"
echo "Access Token: ${ACCESS_TOKEN:0:50}..."
echo "Expires In: $EXPIRES_IN seconds (~1 hour)"
echo "Refresh Token: ${REFRESH_TOKEN:0:30}..."
echo ""

echo "================================================"
echo "Environment Variables"
echo "================================================"
echo ""
echo "Add these to your shell:"
echo ""
echo "export CONFLUENCE_ACCESS_TOKEN='$ACCESS_TOKEN'"
echo ""
echo "Or save to .env file (don't commit!):"
echo ""
echo "CONFLUENCE_ACCESS_TOKEN=$ACCESS_TOKEN"
echo ""

# Offer to test immediately
read -p "Test the token now? (y/n) " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo ""
    echo "Testing token..."
    echo ""
    
    # Get instance URL
    if [ -z "$CONFLUENCE_INSTANCE_URL" ]; then
        read -p "Enter your Confluence instance URL (e.g., https://company.atlassian.net): " INSTANCE_URL
    else
        INSTANCE_URL="$CONFLUENCE_INSTANCE_URL"
    fi
    
    export CONFLUENCE_ACCESS_TOKEN="$ACCESS_TOKEN"
    export CONFLUENCE_INSTANCE_URL="$INSTANCE_URL"
    
    python test_confluence.py
fi

echo ""
echo "✅ Done! Token is ready to use."
echo ""
echo "⚠️  Remember: OAuth tokens expire after 1 hour"
echo "💡 TIP: For testing, consider using API Token instead - it doesn't expire!"
