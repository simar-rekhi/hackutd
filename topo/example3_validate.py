#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Example 3: Validate a client with minimal data
This demonstrates how the system handles clients with limited information.
"""

import os
import sys

# Add current directory to path to import multipersistence
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

# Import from multipersistence module (same directory)
from multipersistence import ClientValidator

def main():
    # Path to saved model artifacts
    script_dir = os.path.dirname(os.path.abspath(__file__))
    model_path = os.path.join(script_dir, "model_artifacts.pkl")
    
    if not os.path.exists(model_path):
        print(f"Error: Model artifacts not found at {model_path}")
        print("Please run multipersistence.py first to train and save the model.")
        print("\nTo train the model, run:")
        print("  python topo/multipersistence.py")
        return
    
    print("Loading model artifacts...")
    validator = ClientValidator(model_path)
    print("Model loaded successfully!\n")
    
    # Example 3: Minimal data client
    print("=" * 60)
    print("Example 3: Minimal Data Client")
    print("=" * 60)
    print("This client only provides an email address.")
    print("The system will still analyze connections in the graph.\n")
    
    client_data = {
        "email": "minimal@example.com",
        # Only email provided - minimal data scenario
    }
    
    print("Client Data Provided:")
    print(f"  Email: {client_data['email']}")
    print()
    
    # Validate client
    result = validator.validate_client(
        client_id="client_minimal_001",
        client_data=client_data,
        return_details=True
    )
    
    print("=" * 60)
    print("Validation Results")
    print("=" * 60)
    print(f"Client ID: client_minimal_001")
    print(f"Status: {result['status']}")
    print(f"Risk Score: {result['risk_score']:.4f}")
    print(f"Triage Category: {result['triage']}")
    
    if 'connections' in result:
        print(f"\nGraph Analysis:")
        print(f"  Connections in Graph: {result['connections']}")
        print(f"  F1 Reuse Risk: {result['f1_reuse_risk']:.4f}")
        if 'f2_proxy' in result:
            print(f"  F2 Proxy Score: {result['f2_proxy']:.4f}")
    
    print("\n" + "=" * 60)
    print("Interpretation:")
    print("=" * 60)
    if result['status'] == "Validated":
        print("✓ Client is VALIDATED - Low risk detected")
        print("  This client can proceed with onboarding.")
    else:
        print("⚠ Client is FLAGGED - Requires review")
        if result['triage'] == "Fraud":
            print("  HIGH RISK: Immediate fraud investigation recommended.")
        elif result['triage'] == "Iffy":
            print("  MEDIUM RISK: Manual review recommended.")
    
    if result['connections'] > 0:
        print(f"\n⚠ Warning: This client shares {result['connections']} identifier(s)")
        print("  with existing clients in the database.")
        print("  This may indicate potential fraud or identity reuse.")
    else:
        print("\n✓ No connections found in existing graph.")
        print("  This is a new client with no shared identifiers.")
    
    return result

if __name__ == "__main__":
    main()

