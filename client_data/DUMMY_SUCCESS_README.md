# Dummy Success Client Dataset

## File: `dummy_success_client.json`

This dataset is **guaranteed to pass validation** in the dashboard. It contains:

### Key Success Factors:

1. **All Required Fields Present:**

   - ✅ Legal Name: SecureTech Solutions Inc
   - ✅ Contact Email: john.smith.securetech@example-success.com
   - ✅ Contact Phone: 302-555-0100
   - ✅ Registered Address: 123 Innovation Drive, Suite 500, Wilmington, DE 19801

2. **Low Risk Indicators:**

   - ✅ AML Risk Rating: **1/5** (Lowest risk)
   - ✅ Credit Score: **750** (Excellent)
   - ✅ PEP Status: **No**
   - ✅ Sanctions Screen: **Clear**
   - ✅ Risk Assessment: **Low**

3. **Unique Identifiers:**

   - Unique email domain: `@example-success.com`
   - Unique phone: `302-555-0100`
   - Unique address: `123 Innovation Drive`
   - Unique Tax ID: `987654321`
   - Unique Registration: `999888777`

   These values are designed to **NOT match any existing clients** in the graph, ensuring zero connections.

4. **Complete Compliance Profile:**
   - All certifications provided
   - Insurance in place
   - SOC2 and ISO27001 certified
   - Clean legal history
   - Proper documentation

### Expected Validation Result:

- **Status:** ✅ **VALIDATED**
- **Triage:** **Clear**
- **Risk Score:** **Low** (< 0.3 expected)
- **Connections:** **0** (no graph connections)
- **Action:** **Approve for onboarding**

### How to Use:

1. Upload this JSON file to your dashboard
2. The system will extract all structured data
3. Validation will run automatically
4. Result will show **VALIDATED** status

### Notes:

- All identifiers are unique and won't match existing clients
- Risk ratings are set to minimum (best case scenario)
- Credit score is excellent (750)
- All compliance requirements are met
- This is a perfect test case for demonstrating successful validation
