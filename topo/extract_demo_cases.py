#!/usr/bin/env python3
import pandas as pd

df = pd.read_excel('global_dataset.xlsx')

# Case 1: Perfect validation case
non_fraud = df[df['fraud_label'] == 'Non-Fraudulent']
best = non_fraud[(non_fraud['credit_score'] >= 700) & (non_fraud['aml_risk_rating'] <= 2)].iloc[0]

print("=" * 80)
print("CASE 1: PERFECT VALIDATION CASE - WILL PASS 100%")
print("=" * 80)
print(f"Legal Name: {best['legal_name']}")
print(f"Contact Email: {best['contact_email']}")
print(f"Contact Phone: {best['contact_phone']}")
print(f"Registered Address: {best['registered_address']}")
print(f"Tax ID Number: {best['tax_id_number']}")
print(f"VAT/GST Registration: {best['vat_gst_registration']}")
print(f"Credit Score: {best['credit_score']}")
print(f"AML Risk Rating: {best['aml_risk_rating']}")
print(f"PEP Status: {best['pep_status']}")
print(f"Sanctions Screen: {best['sanctions_screen_result']}")
print(f"Registration Number: {best['registration_number']}")
print(f"Bank SWIFT Code: {best['bank_swift_code']}")
print(f"Bank Routing Number: {best['bank_routing_number']}")
print(f"Fraud Label: {best['fraud_label']}")
print()

# Case 2: Worst case - will fail
fraud = df[df['fraud_label'] == 'Fraudulent']
worst = fraud.iloc[0]

print("=" * 80)
print("CASE 2: WORST CASE - WILL FAIL VALIDATION")
print("=" * 80)
print(f"Legal Name: {worst['legal_name']}")
print(f"Contact Email: {worst['contact_email']}")
print(f"Contact Phone: {worst['contact_phone']}")
print(f"Registered Address: {worst['registered_address']}")
print(f"Tax ID Number: {worst['tax_id_number']}")
print(f"VAT/GST Registration: {worst['vat_gst_registration']}")
print(f"Credit Score: {worst['credit_score']}")
print(f"AML Risk Rating: {worst['aml_risk_rating']}")
print(f"PEP Status: {worst['pep_status']}")
print(f"Sanctions Screen: {worst['sanctions_screen_result']}")
print(f"Registration Number: {worst['registration_number']}")
print(f"Bank SWIFT Code: {worst['bank_swift_code']}")
print(f"Bank Routing Number: {worst['bank_routing_number']}")
print(f"Fraud Label: {worst['fraud_label']}")
print()

# Export to formatted text for PDF
print("=" * 80)
print("FORMATTED FOR PDF:")
print("=" * 80)
print("\n--- CASE 1: PERFECT VALIDATION CASE ---")
print(f"Legal Name: {best['legal_name']}")
print(f"Email: {best['contact_email']}")
print(f"Phone: {best['contact_phone']}")
print(f"Address: {best['registered_address']}")
print(f"Tax ID: {best['tax_id_number']}")
print(f"Credit Score: {best['credit_score']}")
print(f"AML Risk: {best['aml_risk_rating']}/5")
print(f"PEP: {best['pep_status']}")
print(f"Status: {best['fraud_label']}")

print("\n--- CASE 2: WORST CASE - WILL FAIL ---")
print(f"Legal Name: {worst['legal_name']}")
print(f"Email: {worst['contact_email']}")
print(f"Phone: {worst['contact_phone']}")
print(f"Address: {worst['registered_address']}")
print(f"Tax ID: {worst['tax_id_number']}")
print(f"Credit Score: {worst['credit_score']}")
print(f"AML Risk: {worst['aml_risk_rating']}/5")
print(f"PEP: {worst['pep_status']}")
print(f"Status: {worst['fraud_label']}")

