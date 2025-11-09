"""
Utility functions for Gemini API integration
Handles OCR and data structuring from PDFs
"""
import os
import json
from typing import Dict, Any, Optional
import google.generativeai as genai

# Initialize Gemini API
# Try to load from environment variable first
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

# If not found, try loading from .env file
if not GEMINI_API_KEY:
    try:
        from dotenv import load_dotenv
        load_dotenv()
        GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
    except ImportError:
        pass

# Development fallback - set your API key here if needed (NOT for production!)
# Uncomment and add your key below if environment variable isn't working
if not GEMINI_API_KEY:
    GEMINI_API_KEY = "AIzaSyC-I_aEtZ-rqcJlYRgnu8p-IWIZBDtT38o"

# Configure Gemini if we have a key
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)


def extract_text_from_pdf(pdf_path: str, filename: str) -> str:
    """
    Use Gemini to extract text from PDF via OCR.
    Returns extracted text.
    """
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY environment variable not set. Please set it in your environment.")
    
    try:
        # Create the prompt for OCR
        prompt = f"""
        Please extract all text content from this PDF document ({filename}).
        Extract all visible text, including:
        - Headers and titles
        - Body text
        - Tables and structured data
        - Any numbers, dates, addresses, names, IDs, etc.
        
        Return the extracted text in a clear, structured format.
        If the PDF contains forms or structured data, preserve the structure as much as possible.
        """
        
        # Use Gemini 2.5 Flash for document understanding (faster and cost-effective)
        model = genai.GenerativeModel('gemini-2.5-flash')
        
        # Upload the PDF file to Gemini
        uploaded_file = genai.upload_file(path=pdf_path, mime_type="application/pdf")
        
        # Wait for file to be processed
        import time
        while uploaded_file.state.name == "PROCESSING":
            time.sleep(2)
            uploaded_file = genai.get_file(uploaded_file.name)
        
        if uploaded_file.state.name == "FAILED":
            raise ValueError(f"File upload failed: {uploaded_file.state.name}")
        
        # Generate content with the uploaded PDF
        response = model.generate_content([
            prompt,
            uploaded_file
        ])
        
        # Clean up uploaded file
        try:
            genai.delete_file(uploaded_file.name)
        except:
            pass
        
        return response.text
    
    except Exception as e:
        print(f"Error with PDF extraction: {e}")
        # Try to clean up file if it was uploaded
        try:
            if 'uploaded_file' in locals():
                genai.delete_file(uploaded_file.name)
        except:
            pass
        raise


def structure_extracted_data(extracted_text: str, dataset_columns: list) -> Dict[str, Any]:
    """
    Use Gemini to structure extracted text according to dataset format.
    Returns structured data dictionary matching dataset columns.
    """
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY environment variable not set")
    
    try:
        model = genai.GenerativeModel('gemini-2.5-flash')
        
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
        
        response = model.generate_content(prompt)
        
        # Parse JSON from response
        response_text = response.text.strip()
        
        # Try to extract JSON if wrapped in markdown
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()
        
        structured_data = json.loads(response_text)
        
        # Ensure all dataset columns are present (fill with None if missing)
        result = {}
        for col in dataset_columns:
            result[col] = structured_data.get(col, None)
        
        return result
    
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON from Gemini: {e}")
        print(f"Response was: {response_text[:500]}")
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

