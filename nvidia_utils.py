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
NVIDIA_NIM_API_KEY = os.getenv('NVIDIA_NIM_API_KEY', '')
# Default to user's Brev endpoint, but allow override via env var
# Make sure this matches your Brev instance URL
# Try localhost first if available, otherwise use the Cloudflare tunnel URL
NVIDIA_NIM_BASE_URL = os.getenv('NVIDIA_NIM_BASE_URL', 'http://localhost:8000/v1')
# Fallback to Cloudflare tunnel if localhost doesn't work
NVIDIA_NIM_BASE_URL_FALLBACK = os.getenv('NVIDIA_NIM_BASE_URL_FALLBACK', 'https://8000-uzuj2kk3e.brevlab.com/v1')

# Debug: Print the configuration being used
print(f"NVIDIA NIM Configuration:")
print(f"  Base URL: {NVIDIA_NIM_BASE_URL}")
print(f"  API Key: {'SET' if NVIDIA_NIM_API_KEY else 'NOT SET'}")

# Development fallback - set your API key here if needed (NOT for production!)
if not NVIDIA_NIM_API_KEY:
    NVIDIA_NIM_API_KEY = None  # Set your NVIDIA NIM API key here if needed


def extract_text_from_pdf(pdf_path: str, filename: str) -> str:
    """
    Use NVIDIA Nemotron to extract text from PDF via OCR.
    Sends the PDF directly to Nemotron for processing.
    Returns extracted text.
    """
    try:
        # Read PDF file and convert to base64
        print(f"Reading PDF file: {filename}...")
        with open(pdf_path, 'rb') as pdf_file:
            pdf_data = pdf_file.read()
            pdf_base64 = base64.b64encode(pdf_data).decode('utf-8')
        
        # Use Nemotron model via Brev/NIM
        model_name = os.getenv('NVIDIA_NIM_MODEL', 'nvidia/nvidia-nemotron-nano-9b-v2')
        
        # Create the prompt for OCR
        prompt = f"""
        Please perform OCR (Optical Character Recognition) on this PDF document named "{filename}".
        
        Extract ALL visible text from the entire document, including:
        - Headers and titles
        - Body text and paragraphs
        - Tables and structured data
        - Any numbers, dates, addresses, names, IDs, account numbers, etc.
        - Form fields and their values
        - All pages in the document
        
        Preserve the structure and formatting as much as possible.
        Return ONLY the extracted text, nothing else.
        """
        
        # Prepare the request payload with PDF
        # Try sending PDF as base64 data URL
        payload = {
            "model": model_name,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:application/pdf;base64,{pdf_base64}"
                            }
                        }
                    ]
                }
            ],
            "top_p": 1,
            "max_tokens": 8192,  # Increased for longer documents
            "temperature": 0.1
        }
        
        # Make API request to Brev/NIM
        # Use a session to handle cookies for Cloudflare Access
        session = requests.Session()
        
        headers = {
            "accept": "application/json",
            "Content-Type": "application/json"
        }
        
        # Brev requires authorization header - always include it
        if NVIDIA_NIM_API_KEY:
            headers["Authorization"] = f"Bearer {NVIDIA_NIM_API_KEY}"
        else:
            # Some Brev instances require the header even if empty
            headers["Authorization"] = "Bearer "
        
        # Try localhost first, then fallback to Cloudflare tunnel
        api_urls = [
            f"{NVIDIA_NIM_BASE_URL}/chat/completions",
            f"{NVIDIA_NIM_BASE_URL_FALLBACK}/chat/completions"
        ]
        
        response = None
        last_error = None
        
        for api_url in api_urls:
            try:
                print(f"Trying endpoint: {api_url}...")
                response = session.post(api_url, headers=headers, json=payload, timeout=300)
                
                # Debug: Print response details
                print(f"Response status code: {response.status_code}")
                print(f"Response Content-Type: {response.headers.get('Content-Type', 'unknown')}")
                
                # Check if we got a Cloudflare Access login page
                if response.headers.get('Content-Type', '').startswith('text/html'):
                    print(f"Got HTML response (likely Cloudflare Access login page), trying next endpoint...")
                    last_error = "Cloudflare Access authentication required"
                    continue
                
                # If we got a valid JSON response (or non-HTML), break
                if response.status_code == 200 and not response.headers.get('Content-Type', '').startswith('text/html'):
                    print(f"Successfully connected to {api_url}")
                    break
                elif response.status_code != 200:
                    print(f"Got status {response.status_code}, trying next endpoint...")
                    last_error = f"Status {response.status_code}: {response.text[:200]}"
                    continue
                    
            except requests.exceptions.ConnectionError as e:
                print(f"Connection error to {api_url}: {e}")
                last_error = f"Connection error: {str(e)}"
                continue
            except Exception as e:
                print(f"Error with {api_url}: {e}")
                last_error = str(e)
                continue
        
        # If all endpoints failed or returned HTML
        if response is None or response.headers.get('Content-Type', '').startswith('text/html'):
            error_msg = f"""
            ERROR: Could not connect to Nemotron endpoint.
            
            Tried endpoints:
            1. {api_urls[0]}
            2. {api_urls[1]}
            
            The Cloudflare tunnel endpoint is protected by Cloudflare Access.
            
            Solutions:
            1. Use localhost if your Brev instance is running locally:
               Set NVIDIA_NIM_BASE_URL=http://localhost:8000/v1 in your .env file
               
            2. Get a Cloudflare Access service token:
               - Go to your Brev console
               - Navigate to Cloudflare Access settings
               - Create a Service Token for API access
               - Add it to .env as: NVIDIA_NIM_API_KEY=your-service-token
               
            3. Configure Cloudflare Access to allow API requests:
               - Add a rule that allows requests with Authorization header
               - Or disable Cloudflare Access for API endpoints
               
            Last error: {last_error}
            """
            print(error_msg)
            raise ValueError("Could not connect to Nemotron endpoint. See error message above for solutions.")
        
        print(f"Response text (first 500 chars): {response.text[:500]}")
        
        if response.status_code != 200:
            # Try alternative format - PDF as document attachment
            print(f"First attempt failed ({response.status_code}), trying alternative format...")
            
            # Alternative: Try with PDF in a different format
            payload_alt = {
                "model": model_name,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": prompt
                            },
                            {
                                "type": "document",
                                "document": {
                                    "type": "pdf",
                                    "data": pdf_base64
                                }
                            }
                        ]
                    }
                ],
                "top_p": 1,
                "max_tokens": 8192,
                "temperature": 0.1
            }
            
            # Make sure headers are set for the alternative attempt too
            if "Authorization" not in headers:
                if NVIDIA_NIM_API_KEY:
                    headers["Authorization"] = f"Bearer {NVIDIA_NIM_API_KEY}"
                else:
                    headers["Authorization"] = "Bearer "
            
            response = requests.post(api_url, headers=headers, json=payload_alt, timeout=300)
            print(f"Alternative attempt - Status: {response.status_code}, Response: {response.text[:500]}")
            
            if response.status_code != 200:
                raise ValueError(f"NVIDIA NIM API error: {response.status_code} - {response.text[:1000]}")
        
        # Check if response is valid JSON
        try:
            result = response.json()
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON response from API. Status: {response.status_code}, Response: {response.text[:1000]}")
        
        # Extract the text from the response
        if "choices" in result and len(result["choices"]) > 0:
            extracted_text = result["choices"][0]["message"]["content"]
        else:
            raise ValueError(f"Unexpected response format: {result}")
        
        print(f"Successfully extracted text from PDF using Nemotron OCR")
        return extracted_text
    
    except requests.exceptions.RequestException as e:
        print(f"Error with PDF extraction (network): {e}")
        raise
    except Exception as e:
        print(f"Error with PDF extraction: {e}")
        raise


def structure_extracted_data(extracted_text: str, dataset_columns: list) -> Dict[str, Any]:
    """
    Use NVIDIA Nemotron to structure extracted text according to dataset format.
    Returns structured data dictionary matching dataset columns.
    """
    try:
        # Use Nemotron model via Brev/NIM
        model_name = os.getenv('NVIDIA_NIM_MODEL', 'nvidia/nvidia-nemotron-nano-9b-v2')
        
        # Create column list for prompt
        columns_str = ", ".join(dataset_columns[:50])  # Limit to first 50 for prompt size
        if len(dataset_columns) > 50:
            columns_str += f" ... and {len(dataset_columns) - 50} more columns"
        
        prompt = f"""
        You are extracting structured data from a document for a KYC (Know Your Customer) onboarding system.
        
        Below is the extracted text from a document. Please extract and structure the information according to the following dataset columns:
        
        {columns_str}
        
        Extract the following key information if available:
        - Legal name, DBA name, entity type
        - Registration number, jurisdiction
        - Addresses (registered, operational, mailing)
        - Contact information (name, email, phone, role)
        - Tax IDs, VAT numbers
        - Bank details (name, account, SWIFT, routing)
        - UBO (Ultimate Beneficial Owner) information
        - Directors, authorized signatories
        - Government IDs
        - Risk ratings, credit scores
        - Any other relevant information
        
        Return ONLY a valid JSON object with keys matching the dataset columns.
        Use null for missing fields.
        Use arrays for fields that can have multiple values (like ubo_names, director_list).
        Keep string values as strings, numbers as numbers, dates as strings in YYYY-MM-DD format.
        
        Extracted text:
        {extracted_text[:10000] if len(extracted_text) > 10000 else extracted_text}
        
        Return the JSON object now:
        """
        
        # Prepare the request payload matching Brev's API format
        payload = {
            "model": model_name,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "top_p": 1,
            "max_tokens": 4096,
            "temperature": 0.1  # Lower temperature for more structured output
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
        
        # Extract the text from the response
        if "choices" in result and len(result["choices"]) > 0:
            response_text = result["choices"][0]["message"]["content"]
        else:
            raise ValueError(f"Unexpected response format: {result}")
        
        # Parse JSON from response
        response_text = response_text.strip()
        
        # Try to extract JSON if wrapped in markdown
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()
        
        structured_data = json.loads(response_text)
        
        # Ensure all dataset columns are present (fill with None if missing)
        result_dict = {}
        for col in dataset_columns:
            result_dict[col] = structured_data.get(col, None)
        
        return result_dict
    
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON from Nemotron: {e}")
        print(f"Response was: {response_text[:500] if 'response_text' in locals() else 'N/A'}")
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
    
    # Step 2: Structure the data
    print(f"Structuring data from {filename}...")
    structured_data = structure_extracted_data(extracted_text, dataset_columns)
    
    return {
        "filename": filename,
        "extracted_text": extracted_text,
        "structured_data": structured_data
    }

