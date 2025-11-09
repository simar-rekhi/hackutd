"""
Utility functions for NVIDIA NIM (NVIDIA Inference Microservices) and Nemotron models
Handles OCR and data structuring from PDFs
"""
import os
import json
import base64
import requests
from typing import Dict, Any, Optional

# Initialize NVIDIA NIM API (Brev deployment)
# Load .env file first if available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Get configuration from environment variables
# These are SEPARATE servers - configure them independently

# Nemotron-Parse VLM Server (for PDF/image OCR processing)
# This is a different server from the LLM server
NVIDIA_NIM_VLM_API_KEY = os.getenv('NVIDIA_NIM_VLM_API_KEY', os.getenv('NVIDIA_NIM_API_KEY', ''))
NVIDIA_NIM_VLM_BASE_URL = os.getenv('NVIDIA_NIM_VLM_BASE_URL', 'http://localhost:9000/v1')
NVIDIA_NIM_VLM_BASE_URL_FALLBACK = os.getenv('NVIDIA_NIM_VLM_BASE_URL_FALLBACK', '')

# Regular Nemotron LLM Server (for text processing and data structuring)
# This is a different server from the VLM server
NVIDIA_NIM_API_KEY = os.getenv('NVIDIA_NIM_API_KEY', '')
NVIDIA_NIM_BASE_URL = os.getenv('NVIDIA_NIM_BASE_URL', 'http://localhost:8000/v1')
NVIDIA_NIM_BASE_URL_FALLBACK = os.getenv('NVIDIA_NIM_BASE_URL_FALLBACK', 'https://8000-uzuj2kk3e.brevlab.com/v1')

# Debug: Print the configuration being used
print(f"NVIDIA NIM Configuration:")
print(f"  VLM Server (Nemotron-Parse for PDF/Images): {NVIDIA_NIM_VLM_BASE_URL}")
print(f"    VLM API Key: {'SET' if NVIDIA_NIM_VLM_API_KEY else 'NOT SET'}")
print(f"  LLM Server (Nemotron for Text Processing): {NVIDIA_NIM_BASE_URL}")
print(f"    LLM API Key: {'SET' if NVIDIA_NIM_API_KEY else 'NOT SET'}")

# Development fallback - set your API key here if needed (NOT for production!)
if not NVIDIA_NIM_API_KEY:
    NVIDIA_NIM_API_KEY = None  # Set your NVIDIA NIM API key here if needed


def extract_text_from_pdf(pdf_path: str, filename: str) -> str:
    """
    Use NVIDIA Nemotron-Parse VLM to extract text from PDF via OCR.
    Converts PDF pages to images and uses Nemotron-Parse tools for extraction.
    Returns extracted text.
    """
    try:
        # Convert PDF to images first (Nemotron-Parse works with images, not PDFs directly)
        try:
            from pdf2image import convert_from_path
            from io import BytesIO
            import PIL.Image
            import mimetypes
        except ImportError:
            raise ImportError("pdf2image and Pillow are required. Install: pip install pdf2image Pillow")
        
        print(f"Converting PDF to images: {filename}...")
        images = convert_from_path(pdf_path, dpi=200)
        
        if not images:
            raise ValueError("No pages found in PDF")
        
        print(f"Found {len(images)} pages, processing with Nemotron-Parse...")
        
        # Use Nemotron-Parse VLM model
        vlm_model_name = os.getenv('NVIDIA_NIM_VLM_MODEL', 'nvidia/nemotron-parse')
        
        # Nemotron-Parse tools for different extraction modes
        tools = [
            "markdown_bbox",      # Extract with bounding boxes
            "markdown_no_bbox",   # Extract without bounding boxes (cleaner text)
            "detection_only",     # Detection only
        ]
        
        # Use markdown_no_bbox for clean text extraction (tool index 1)
        tool_id = 1  # markdown_no_bbox
        tool_name = tools[tool_id]
        
        # Process each page
        all_extracted_text = []
        
        for page_num, image in enumerate(images, 1):
            print(f"Processing page {page_num}/{len(images)}...")
            
            # Convert image to base64
            buffered = BytesIO()
            image.save(buffered, format="PNG")
            img_base64 = base64.b64encode(buffered.getvalue()).decode('ascii')
            mime = "image/png"
            
            # Use Nemotron-Parse format: embed image as HTML-like tag
            media_tag = f'<img src="data:{mime};base64,{img_base64}" />'
            content = media_tag
            
            # Prepare tool specification
            tool_spec = [{"type": "function", "function": {"name": tool_name}}]
            
            # Prepare payload in Nemotron-Parse format
            payload = {
                "model": vlm_model_name,
                "messages": [
                    {
                        "role": "user",
                        "content": content
                    }
                ],
                "tools": tool_spec,
                "tool_choice": {"type": "function", "function": {"name": tool_name}},
                "max_tokens": 8192,  # Increased for longer documents
            }
            
            # Make API request to Nemotron-Parse VLM endpoint (separate server)
            session = requests.Session()
            
            headers = {
                "Accept": "application/json",
                "Content-Type": "application/json"
            }
            
            # Use VLM-specific API key if available, otherwise fall back to general key
            vlm_api_key = NVIDIA_NIM_VLM_API_KEY if NVIDIA_NIM_VLM_API_KEY else NVIDIA_NIM_API_KEY
            if vlm_api_key:
                headers["Authorization"] = f"Bearer {vlm_api_key}"
            else:
                headers["Authorization"] = "Bearer "
            
            # Try VLM server endpoint for PDF processing
            api_urls = [f"{NVIDIA_NIM_VLM_BASE_URL}/chat/completions"]
            if NVIDIA_NIM_VLM_BASE_URL_FALLBACK:
                api_urls.append(f"{NVIDIA_NIM_VLM_BASE_URL_FALLBACK}/chat/completions")
            
            page_response = None
            page_error = None
            
            for api_url in api_urls:
                try:
                    print(f"  Sending to: {api_url}...")
                    page_response = session.post(api_url, headers=headers, json=payload, timeout=300)
                    
                    # Check if we got a Cloudflare Access login page
                    if page_response.headers.get('Content-Type', '').startswith('text/html'):
                        print(f"  Got HTML response (Cloudflare Access), trying next endpoint...")
                        page_error = "Cloudflare Access authentication required"
                        continue
                    
                    # If we got a valid response, break
                    if page_response.status_code == 200 and not page_response.headers.get('Content-Type', '').startswith('text/html'):
                        break
                    elif page_response.status_code != 200:
                        print(f"  Got status {page_response.status_code}, trying next endpoint...")
                        page_error = f"Status {page_response.status_code}: {page_response.text[:200]}"
                        continue
                        
                except requests.exceptions.ConnectionError as e:
                    print(f"  Connection error: {e}")
                    page_error = f"Connection error: {str(e)}"
                    continue
                except Exception as e:
                    print(f"  Error: {e}")
                    page_error = str(e)
                    continue
            
            # Process the response
            if page_response is None or page_response.headers.get('Content-Type', '').startswith('text/html'):
                raise ValueError(f"Could not connect to Nemotron-Parse endpoint. Error: {page_error}")
            
            if page_response.status_code != 200:
                raise ValueError(f"NVIDIA NIM API error: {page_response.status_code} - {page_response.text[:1000]}")
            
            # Parse response
            try:
                page_result = page_response.json()
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON response. Status: {page_response.status_code}, Response: {page_response.text[:1000]}")
            
            # Extract text from Nemotron-Parse response
            # Nemotron-Parse returns tool calls with the extracted text
            if "choices" in page_result and len(page_result["choices"]) > 0:
                choice = page_result["choices"][0]
                
                # Check if there's a tool call with the result
                if "message" in choice:
                    message = choice["message"]
                    
                    # Nemotron-Parse returns results in tool_calls
                    if "tool_calls" in message and len(message["tool_calls"]) > 0:
                        # Extract from tool call arguments
                        tool_call = message["tool_calls"][0]
                        if "function" in tool_call and "arguments" in tool_call["function"]:
                            try:
                                args = json.loads(tool_call["function"]["arguments"])
                                if "markdown" in args:
                                    page_text = args["markdown"]
                                elif "text" in args:
                                    page_text = args["text"]
                                else:
                                    page_text = str(args)
                            except:
                                page_text = str(tool_call["function"].get("arguments", ""))
                        else:
                            page_text = str(tool_call)
                    # Or check if content is directly in message
                    elif "content" in message:
                        page_text = message["content"]
                    else:
                        page_text = str(message)
                else:
                    page_text = str(choice)
                
                all_extracted_text.append(f"--- Page {page_num} ---\n{page_text}\n")
            else:
                print(f"Warning: Unexpected response format for page {page_num}")
        
        if not all_extracted_text:
            raise ValueError("Failed to extract text from any pages")
        
        # Combine all pages
        extracted_text = "\n".join(all_extracted_text)
        print(f"Successfully extracted text from {len(images)} pages using Nemotron-Parse")
        return extracted_text
    
    except requests.exceptions.RequestException as e:
        print(f"Error with PDF extraction (network): {e}")
        raise
    except Exception as e:
        print(f"Error with PDF extraction: {e}")
        raise


def _create_json_schema_from_columns(dataset_columns: list) -> Dict[str, Any]:
    """
    Convert a list of column names into a JSON schema for structured output.
    Each column is treated as a string property (can be null).
    """
    properties = {}
    for col in dataset_columns:
        properties[col] = {
            "type": ["string", "null"],
            "description": f"Extracted value for {col}"
        }
    
    return {
        "type": "object",
        "properties": properties,
        "required": dataset_columns,  # All columns are required (but can be null)
        "additionalProperties": False
    }


def structure_extracted_data(extracted_text: str, dataset_columns: list) -> Dict[str, Any]:
    """
    Use NVIDIA Nemotron to structure extracted text according to dataset format.
    Uses structured output API to ensure valid JSON schema compliance.
    Returns structured data dictionary matching dataset columns.
    """
    try:
        # Use Nemotron model via Brev/NIM
        model_name = os.getenv('NVIDIA_NIM_MODEL', 'nvidia/nvidia-nemotron-nano-9b-v2')
        
        # Create JSON schema from dataset columns
        json_schema = _create_json_schema_from_columns(dataset_columns)
        
        # Create system prompt for extraction guidance
        prompt = """You are an expert system for extracting structured KYC (Know Your Customer) and Due Diligence data from unstructured or semi-structured documents such as onboarding forms, company profiles, certificates, compliance reports, or financial statements.

Your task is to identify and extract all relevant entity attributes, ensuring maximum recall (extract every potentially relevant value) and clean, normalized output.
The final output must be one JSON object with all keys present, corresponding exactly to the provided schema.
Use null for missing data.
If multiple values exist (e.g., multiple UBOs or directors), represent them as arrays (as strings containing JSON arrays).

INSTRUCTIONS:

1. Read and interpret the text contextually — account for multiple sections, embedded tables, and variations in terminology.
   - For example, "TIN," "EIN," or "PAN" can map to tax_id_number.
   - "Main office," "HQ," or "Headquarters" can map to registered_address.
2. Capture every value that could be relevant to any listed attribute.
3. Use exact key names from the provided schema.
4. Keep:
   - Strings as plain text.
   - Numeric fields as strings containing numbers where appropriate.
   - Dates in YYYY-MM-DD format if identifiable.
5. Include nested or inferred details when applicable (e.g., extract issuer from a certificate or bank name from a SWIFT code).
6. Include explicit nulls for unavailable fields.
7. Maintain completeness and consistency.

When extracting:
- Addresses: detect variations (registered, operational, mailing) using context keywords (e.g., "registered office," "branch address," "correspondence address").
- UBOs: include every beneficial owner's name, DOB, nationality, and ownership \% as aligned arrays.
- Risk indicators: identify values related to AML risk, PEP, sanctions, adverse media, etc.
- Bank details: include masked accounts, SWIFT, routing, and beneficiary details.
- Compliance & security: extract presence or absence of certifications (ISO27001, SOC2), data handling standards, recovery plans, etc.
- Legal & contractual: detect NDA/MSA status, service scope, audit rights, termination clauses, and notification policies.
- Operational & financial: capture payment terms, pricing, currency, credit score, limits, fees, and SLAs.
- Technical: record API access, integration needs, authentication methods, and testing environments."""
        
        # Prepare the request payload for structured output API
        # Truncate extracted text if too long
        user_content = extracted_text[:10000] if len(extracted_text) > 10000 else extracted_text
        
        payload = {
            "model": model_name,
            "messages": [
                {
                    "role": "system",
                    "content": prompt
                },
                {
                    "role": "user",
                    "content": user_content
                }
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "kyc_extraction",
                    "schema": json_schema,
                    "strict": True
                }
            }
        }
        
        # Make API request to Brev/NIM
        headers = {
            "accept": "application/json",
            "Content-Type": "application/json"
        }
        
        # Brev requires authorization header - use API key or empty bearer token
        if NVIDIA_NIM_API_KEY:
            headers["Authorization"] = f"Bearer {NVIDIA_NIM_API_KEY}"
        else:
            # Try with empty bearer token (some Brev instances allow this)
            headers["Authorization"] = "Bearer "
        
        api_url = f"{NVIDIA_NIM_BASE_URL}/chat/completions"
        
        response = requests.post(api_url, headers=headers, json=payload, timeout=120)
        
        if response.status_code != 200:
            raise ValueError(f"NVIDIA NIM API error: {response.status_code} - {response.text}")
        
        result = response.json()
        
        # Structured output API should return the structured data directly
        # The exact format may vary, but typically it's in a 'output' or 'text' field
        structured_data = None
        
        if "output" in result:
            # Check if output is a string that needs parsing
            structured_data = result["output"]
        elif "text" in result:
            structured_data = result["text"]
        elif "choices" in result and len(result["choices"]) > 0:
            # Fallback to chat completions format if API still uses it
            choice = result["choices"][0]
            if "message" in choice and "content" in choice["message"]:
                content = choice["message"]["content"]
                structured_data = content
        else:
            # Try parsing the entire result as JSON if it's the structured data
            structured_data = result
        
        thing = "</think>"

        if structured_data is not None:
            try:
                start_index = structured_data.index(thing)
                if start_index != -1:
                    start_index += len(thing)
                    structured_data = structured_data[start_index:]
            except ValueError:
                pass

        structured_data = structured_data.strip()

        try:
            structured_data = json.loads(structured_data)
        except json.JSONDecodeError:
            pass
        
        # Ensure all dataset columns are present (fill with None if missing)
        result_dict = {}
        for col in dataset_columns:
            if isinstance(structured_data, dict):
                result_dict[col] = structured_data.get(col, None)
            else:
                result_dict[col] = None
        
        return result_dict
    
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON from Nemotron: {e}")
        print(f"Response was: {result if 'result' in locals() else 'N/A'}")
        # Return empty structure
        return {col: None for col in dataset_columns}
    except Exception as e:
        print(f"Error structuring data: {e}")
        raise


def process_pdf_file(pdf_path: str, dataset_columns: list) -> Dict[str, Any]:
    """
    Complete pipeline: Extract text from PDF, then structure it.
    Returns structured data dictionary.
    """
    filename = os.path.basename(pdf_path)
    
    # Step 1: Extract text via OCR
    print(f"Extracting text from {filename}...")
    extracted_text = extract_text_from_pdf(pdf_path, filename)
    print(f"Extracted text: {extracted_text}")
    
    # Step 2: Structure the data
    print(f"Structuring data from {filename}...")
    structured_data = structure_extracted_data(extracted_text, dataset_columns)
    print(f"Structured data: {structured_data}")
    
    return {
        "filename": filename,
        "extracted_text": extracted_text,
        "structured_data": structured_data
    }

