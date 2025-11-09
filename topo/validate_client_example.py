#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Example script to validate new clients using the trained model.
Uses JSON files from the client_data folder instead of dummy examples.
Run this after training the model with main().
"""

import os
import sys
import json

# Add parent directory to path to import multipersistence
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from topo.multipersistence import ClientValidator, validate_client_from_json

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
    
    # Get client_data directory
    parent_dir = os.path.dirname(script_dir)
    client_data_dir = os.path.join(parent_dir, "client_data")
    
    if not os.path.exists(client_data_dir):
        print(f"Error: client_data directory not found at {client_data_dir}")
        return
    
    # Find all JSON files in client_data directory
    json_files = [f for f in os.listdir(client_data_dir) if f.endswith('.json')]
    
    if not json_files:
        print(f"Error: No JSON files found in {client_data_dir}")
        return
    
    print("Loading model artifacts...")
    validator = ClientValidator(model_path)
    print("Model loaded successfully!\n")
    
    print(f"Found {len(json_files)} JSON file(s) in client_data directory")
    print("=" * 60)
    print()
    
    results = []
    
    # Validate each JSON file
    for i, json_file in enumerate(json_files, 1):
        json_path = os.path.join(client_data_dir, json_file)
        print("=" * 60)
        print(f"Example {i}: Validating client from {json_file}")
        print("=" * 60)
        print(f"File path: {json_path}")
        
        try:
            # Load JSON file
            with open(json_path, 'r', encoding='utf-8') as f:
                json_data = json.load(f)
            
            # Extract client_id and structured_data
            client_id = json_data.get("client_data_id") or json_data.get("client_id") or json_data.get("id")
            if not client_id:
                client_id = os.path.splitext(json_file)[0]  # Use filename without extension
            
            structured_data = json_data.get("structured_data", {})
            if not structured_data:
                structured_data = {k: v for k, v in json_data.items() 
                                if k not in ["client_data_id", "client_id", "id", "created_at", "updated_at", "filename"]}
            
            # Filter out None values
            client_data = {k: v for k, v in structured_data.items() if v is not None}
            
            print(f"Client ID: {client_id}")
            print(f"Fields with data: {len(client_data)} out of {len(structured_data)}")
            
            # Validate client using the validator
            result = validator.validate_client(
                client_id=str(client_id),
                client_data=client_data,
                return_details=True
            )
            
            print(f"\nStatus: {result['status']}")
            print(f"Risk Score: {result['risk_score']:.4f}")
            print(f"Triage: {result['triage']}")
            if 'connections' in result:
                print(f"Graph Connections: {result['connections']}")
                print(f"F1 Reuse Risk: {result['f1_reuse_risk']:.4f}")
                print(f"F2 Proxy: {result['f2_proxy']:.4f}")
            
            result["client_id"] = str(client_id)
            results.append(result)
            
        except Exception as e:
            print(f"\nError validating {json_file}: {e}")
            import traceback
            traceback.print_exc()
            results.append({
                "client_id": json_file,
                "status": "Error",
                "error": str(e)
            })
        
        print()
    
    # Summary
    print("=" * 60)
    print("Summary")
    print("=" * 60)
    for i, result in enumerate(results, 1):
        if "error" in result:
            print(f"Client {i} ({result.get('client_id', 'unknown')}): Error - {result.get('error', 'Unknown error')}")
        else:
            print(f"Client {i} ({result.get('client_id', 'unknown')}): {result.get('status', 'Unknown')} ({result.get('triage', 'Unknown')}) - Risk Score: {result.get('risk_score', 'N/A'):.4f}")

if __name__ == "__main__":
    main()

