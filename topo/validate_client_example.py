#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Example script to validate new clients using the trained model.
Run this after training the model with main().
"""

import os
import sys

# Add parent directory to path to import multipersistence
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from topo.multipersistence import ClientValidator

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
    
    # Example 1: Low-risk client (should be validated)
    print("=" * 60)
    print("Example 1: Low-Risk Client")
    print("=" * 60)
    client1 = {
        "email": "john.doe@example.com",
        "phone": "555-0100",
        "address": "123 Main Street, New York, NY 10001",
        "tax_id": "12-3456789",
        # Add f2 column if your dataset has it (e.g., credit_score)
        # "credit_score": 750
    }
    
    result1 = validator.validate_client(
        client_id="client_001",
        client_data=client1,
        return_details=True
    )
    
    print(f"Client ID: client_001")
    print(f"Status: {result1['status']}")
    print(f"Risk Score: {result1['risk_score']:.4f}")
    print(f"Triage: {result1['triage']}")
    if 'connections' in result1:
        print(f"Graph Connections: {result1['connections']}")
        print(f"F1 Reuse Risk: {result1['f1_reuse_risk']:.4f}")
        print(f"F2 Proxy: {result1['f2_proxy']:.4f}")
    print()
    
    # Example 2: Medium-risk client (might be flagged)
    print("=" * 60)
    print("Example 2: Medium-Risk Client (Shared Identifiers)")
    print("=" * 60)
    client2 = {
        "email": "suspicious@example.com",
        "phone": "555-9999",
        "address": "456 Oak Avenue, Los Angeles, CA 90001",
        "bank_swift_code": "CHASUS33",  # Shared bank code might indicate risk
        # "credit_score": 580
    }
    
    result2 = validator.validate_client(
        client_id="client_002",
        client_data=client2,
        return_details=True
    )
    
    print(f"Client ID: client_002")
    print(f"Status: {result2['status']}")
    print(f"Risk Score: {result2['risk_score']:.4f}")
    print(f"Triage: {result2['triage']}")
    if 'connections' in result2:
        print(f"Graph Connections: {result2['connections']}")
        print(f"F1 Reuse Risk: {result2['f1_reuse_risk']:.4f}")
        print(f"F2 Proxy: {result2['f2_proxy']:.4f}")
    print()
    
    # Example 3: High-risk client (likely flagged)
    print("=" * 60)
    print("Example 3: High-Risk Client (Multiple Shared Identifiers)")
    print("=" * 60)
    client3 = {
        "email": "highrisk@example.com",
        "phone": "555-7777",
        "address": "789 Pine Road, Chicago, IL 60601",
        "tax_id": "98-7654321",
        "vat_id": "VAT123456",
        "bank_routing_number": "021000021",
        # "credit_score": 450
    }
    
    result3 = validator.validate_client(
        client_id="client_003",
        client_data=client3,
        return_details=True
    )
    
    print(f"Client ID: client_003")
    print(f"Status: {result3['status']}")
    print(f"Risk Score: {result3['risk_score']:.4f}")
    print(f"Triage: {result3['triage']}")
    if 'connections' in result3:
        print(f"Graph Connections: {result3['connections']}")
        print(f"F1 Reuse Risk: {result3['f1_reuse_risk']:.4f}")
        print(f"F2 Proxy: {result3['f2_proxy']:.4f}")
    print()
    
    # Example 4: Minimal data client
    print("=" * 60)
    print("Example 4: Minimal Data Client")
    print("=" * 60)
    client4 = {
        "email": "minimal@example.com",
        # Only email provided
    }
    
    result4 = validator.validate_client(
        client_id="client_004",
        client_data=client4,
        return_details=True
    )
    
    print(f"Client ID: client_004")
    print(f"Status: {result4['status']}")
    print(f"Risk Score: {result4['risk_score']:.4f}")
    print(f"Triage: {result4['triage']}")
    if 'connections' in result4:
        print(f"Graph Connections: {result4['connections']}")
        print(f"F1 Reuse Risk: {result4['f1_reuse_risk']:.4f}")
        print(f"F2 Proxy: {result4['f2_proxy']:.4f}")
    print()
    
    print("=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"Client 001: {result1['status']} ({result1['triage']})")
    print(f"Client 002: {result2['status']} ({result2['triage']})")
    print(f"Client 003: {result3['status']} ({result3['triage']})")
    print(f"Client 004: {result4['status']} ({result4['triage']})")

if __name__ == "__main__":
    main()

