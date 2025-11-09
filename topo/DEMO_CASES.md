# Demo Cases for Client Validation System

## CASE 1: PERFECT VALIDATION CASE

**Expected Result: ✅ VALIDATED - Will Pass 100%**

This case represents an ideal client with low risk indicators and unique identifiers.

### Client Information

- **Legal Name:** Allen-Espinoza Ltd
- **Contact Email:** turnermichael@ford.net
- **Contact Phone:** 184-358-7630x249
- **Registered Address:** 06162 Martinez Manor Apt. 440, Tinamouth, MD 83362
- **Registration Number:** 94214382
- **Tax ID Number:** 9639245200
- **VAT/GST Registration:** Not Registered
- **Bank SWIFT Code:** TGELYFRY
- **Bank Routing Number:** 669462919

### Risk Indicators

- **Credit Score:** 700 (Good)
- **AML Risk Rating:** 1/5 (Low Risk)
- **PEP Status:** No
- **Sanctions Screen:** Clear
- **Fraud Label:** Non-Fraudulent

### Why This Will Pass

- Low AML risk rating (1/5)
- Good credit score (700)
- No PEP associations
- Clear sanctions screening
- Unique identifiers with no graph connections expected
- Clean compliance profile

---

## CASE 2: WORST CASE - WILL FAIL VALIDATION

**Expected Result: ❌ FLAGGED - Will Fail Even with Pre-checks**

This case represents a high-risk client with multiple red flags that should trigger immediate rejection.

### Client Information

- **Legal Name:** Bennett, Brown and Castro Ltd
- **Contact Email:** watkinsdaniel@mitchell.biz
- **Contact Phone:** 001-703-914-1436x937
- **Registered Address:** 3529 Kaitlyn Vista, New Justinton, MS 44708
- **Registration Number:** 39958838
- **Tax ID Number:** 9703905715
- **VAT/GST Registration:** Registered
- **Bank SWIFT Code:** XORDMCRJ
- **Bank Routing Number:** 990566476

### Risk Indicators

- **Credit Score:** 740 (Good - but offset by other risks)
- **AML Risk Rating:** 5/5 (Maximum Risk)
- **PEP Status:** No
- **Sanctions Screen:** Clear
- **Fraud Label:** Fraudulent

### Why This Will Fail

- Maximum AML risk rating (5/5) - critical red flag
- Marked as Fraudulent in training data
- High likelihood of shared identifiers in graph (connections to other fraudulent entities)
- Despite good credit score, the AML risk rating and fraud label indicate systemic issues
- Topological analysis will likely detect connections to other flagged entities
- Multiple risk factors compound to create unacceptable risk profile

### Expected Validation Outcome

- **Status:** FLAGGED
- **Triage Category:** Fraud (High Risk)
- **Risk Score:** High (likely > 0.8)
- **Action Required:** Immediate fraud investigation, rejection recommended

---

## Summary

| Case   | Credit Score | AML Risk | Expected Status | Key Differentiator                               |
| ------ | ------------ | -------- | --------------- | ------------------------------------------------ |
| Case 1 | 700          | 1/5      | ✅ Validated    | Low risk profile, unique identifiers             |
| Case 2 | 740          | 5/5      | ❌ Flagged      | Maximum AML risk, fraud label, graph connections |

**Note:** These cases are extracted from the actual training dataset and represent real-world scenarios the model was trained on.
