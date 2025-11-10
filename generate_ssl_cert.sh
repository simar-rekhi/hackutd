#!/bin/bash
# Generate self-signed SSL certificate for local development

echo "Generating self-signed SSL certificate for HTTPS..."

# Create certs directory if it doesn't exist
mkdir -p certs

# Generate private key
openssl genrsa -out certs/key.pem 2048

# Generate certificate
openssl req -new -x509 -key certs/key.pem -out certs/cert.pem -days 365 -subj "/CN=172.20.10.6"

echo ""
echo "✅ SSL certificate generated!"
echo "Certificate: certs/cert.pem"
echo "Private Key: certs/key.pem"
echo ""
echo "You can now run Flask with HTTPS support."

