#!/bin/bash
# Helper script to generate Auth0 URLs for current IP address

IP=$(ifconfig | grep "inet " | grep -v 127.0.0.1 | awk '{print $2}' | head -1)

if [ -z "$IP" ]; then
    echo "Could not determine IP address"
    exit 1
fi

echo "=========================================="
echo "Auth0 Configuration URLs"
echo "=========================================="
echo ""
echo "Your current IP address: $IP"
echo ""
echo "Copy and paste these into Auth0 Dashboard:"
echo ""
echo "--- Allowed Callback URLs ---"
echo "http://localhost:5000/dashboard,"
echo "http://127.0.0.1:5000/dashboard,"
echo "http://$IP:5000/dashboard,"
echo "http://$IP:5000/login,"
echo "http://localhost:5000/login,"
echo "http://127.0.0.1:5000/login"
echo ""
echo "--- Allowed Logout URLs ---"
echo "http://localhost:5000/login,"
echo "http://127.0.0.1:5000/login,"
echo "http://$IP:5000/login"
echo ""
echo "--- Allowed Web Origins ---"
echo "http://localhost:5000,"
echo "http://127.0.0.1:5000,"
echo "http://$IP:5000"
echo ""
echo "=========================================="
echo "Access your app from second device:"
echo "http://$IP:5000"
echo "=========================================="

