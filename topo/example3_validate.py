#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Diverse Client Validation Examples
This script demonstrates various client validation scenarios including:
- Minimal data clients
- Clean clients with complete data
- Clients with shared identifiers (risk indicators)
- Partial/missing data handling
- International clients
- Business information scenarios
"""

import os
import sys

# Add current directory to path to import multipersistence
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

# Import from multipersistence module (same directory)
from multipersistence import ClientValidator

def validate_and_print(validator, client_id, client_data, description):
    """Helper function to validate a client and print results."""
    print("=" * 70)
    print(f"Example: {description}")
    print("=" * 70)
    
    print("\nClient Data Provided:")
    for key, value in client_data.items():
        if value is not None and str(value).strip():
            print(f"  {key}: {value}")
    print()
    
    # Validate client
    result = validator.validate_client(
        client_id=client_id,
        client_data=client_data,
        return_details=True
    )
    
    print("-" * 70)
    print("Validation Results")
    print("-" * 70)
    print(f"Client ID: {client_id}")
    print(f"Status: {result['status']}")
    print(f"Risk Score: {result['risk_score']:.4f}")
    print(f"Triage Category: {result['triage']}")
    
    if 'connections' in result:
        print(f"\nGraph Analysis:")
        print(f"  Connections in Graph: {result['connections']}")
        print(f"  F1 Reuse Risk: {result['f1_reuse_risk']:.4f}")
        if 'f2_proxy' in result:
            print(f"  F2 Proxy Score: {result['f2_proxy']:.4f}")
    
    print("\nInterpretation:")
    if result['status'] == "Validated":
        print("  ✓ VALIDATED - Low risk detected. Client can proceed.")
    else:
        print("  ⚠ FLAGGED - Requires review")
        if result['triage'] == "Fraud":
            print("     HIGH RISK: Immediate fraud investigation recommended.")
        elif result['triage'] == "Iffy":
            print("     MEDIUM RISK: Manual review recommended.")
    
    if result.get('connections', 0) > 0:
        print(f"  ⚠ Warning: Shares {result['connections']} identifier(s) with existing clients.")
    else:
        print("  ✓ No connections found - new client with unique identifiers.")
    
    print()
    return result

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
    print("Running diverse validation examples...\n")
    
    results = []
    
    # Example 1: Minimal data client (only email)
    client1 = {
        "email": "minimal@example.com",
    }
    result1 = validate_and_print(
        validator, "client_001", client1,
        "Minimal Data - Email Only"
    )
    results.append(("Minimal Data", result1))
    
    # Example 2: Clean client with complete data, no connections expected
    client2 = {
        "email": "clean.newclient@example.com",
        "phone": "555-1234",
        "address": "123 Unique Street, New York, NY 10001",
        "tax_id": "99-8887777",
    }
    result2 = validate_and_print(
        validator, "client_002", client2,
        "Clean Client - Complete Data, No Shared Identifiers"
    )
    results.append(("Clean Client", result2))
    
    # Example 3: Client with shared bank information (potential risk)
    client3 = {
        "email": "suspicious.bank@example.com",
        "phone": "555-5678",
        "bank_swift_code": "CHASUS33",  # Common bank code
        "bank_routing_number": "021000021",
    }
    result3 = validate_and_print(
        validator, "client_003", client3,
        "Shared Bank Information - Potential Risk Indicator"
    )
    results.append(("Shared Bank Info", result3))
    
    # Example 4: Client with multiple shared identifiers (high risk)
    client4 = {
        "email": "highrisk.multi@example.com",
        "phone": "555-9999",
        "address": "456 Shared Avenue, Los Angeles, CA 90001",
        "tax_id": "11-2233445",
        "vat_id": "VAT987654",
        "bank_swift_code": "WELLSFARGO",
    }
    result4 = validate_and_print(
        validator, "client_004", client4,
        "Multiple Shared Identifiers - High Risk Scenario"
    )
    results.append(("Multiple Shared IDs", result4))
    
    # Example 5: Client with partial/missing data
    client5 = {
        "email": "partial@example.com",
        "phone": "",  # Empty string
        "address": None,  # None value
        "tax_id": "12-3456789",
    }
    result5 = validate_and_print(
        validator, "client_005", client5,
        "Partial Data - Some Fields Missing or Empty"
    )
    results.append(("Partial Data", result5))
    
    # Example 6: Client with only phone number
    client6 = {
        "phone": "555-2468",
    }
    result6 = validate_and_print(
        validator, "client_006", client6,
        "Single Identifier - Phone Number Only"
    )
    results.append(("Phone Only", result6))
    
    # Example 7: Client with address and tax ID
    client7 = {
        "address": "789 Business Park, Chicago, IL 60601",
        "tax_id": "88-7766554",
        "vat_id": "VAT112233",
    }
    result7 = validate_and_print(
        validator, "client_007", client7,
        "Business Information - Address, Tax ID, VAT"
    )
    results.append(("Business Info", result7))
    
    # Example 8: Client with international identifiers
    client8 = {
        "email": "international@example.com",
        "phone": "+44-20-7946-0958",  # UK format
        "iban": "GB82WEST12345698765432",
        "vat_id": "GB123456789",
    }
    result8 = validate_and_print(
        validator, "client_008", client8,
        "International Client - IBAN and International Format"
    )
    results.append(("International", result8))
    
    # Summary
    print("=" * 70)
    print("SUMMARY - All Validation Results")
    print("=" * 70)
    print(f"{'Example':<25} {'Status':<12} {'Risk Score':<12} {'Triage':<10} {'Connections':<12}")
    print("-" * 70)
    for name, result in results:
        status = result['status']
        risk = f"{result['risk_score']:.4f}"
        triage = result['triage']
        connections = result.get('connections', 0)
        print(f"{name:<25} {status:<12} {risk:<12} {triage:<10} {connections:<12}")
    
    print("\n" + "=" * 70)
    print("Risk Distribution:")
    validated = sum(1 for _, r in results if r['status'] == "Validated")
    flagged = sum(1 for _, r in results if r['status'] == "Flagged")
    fraud = sum(1 for _, r in results if r['triage'] == "Fraud")
    iffy = sum(1 for _, r in results if r['triage'] == "Iffy")
    clear = sum(1 for _, r in results if r['triage'] == "Clear")
    
    print(f"  Validated: {validated}/{len(results)}")
    print(f"  Flagged: {flagged}/{len(results)}")
    print(f"  Triage Breakdown:")
    print(f"    - Clear: {clear}")
    print(f"    - Iffy: {iffy}")
    print(f"    - Fraud: {fraud}")
    print("=" * 70)
    
    return results

if __name__ == "__main__":
    main()

