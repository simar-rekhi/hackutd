# Setup Instructions

## Prerequisites

1. Python 3.8 or higher
2. A Google Gemini API key

## Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Set up your Gemini API key:
   - Get your API key from [Google AI Studio](https://makersuite.google.com/app/apikey)
   - Set it as an environment variable:
   
   **On macOS/Linux:**
   ```bash
   export GEMINI_API_KEY="your-api-key-here"
   ```
   
   **On Windows:**
   ```cmd
   set GEMINI_API_KEY=your-api-key-here
   ```
   
   **Or create a `.env` file** (recommended):
   ```
   GEMINI_API_KEY=your-api-key-here
   ```
   
   Then install python-dotenv and load it in main.py:
   ```bash
   pip install python-dotenv
   ```

## Running the Application

1. Start the Flask server:
```bash
python main.py
```

2. Open your browser and navigate to:
```
http://localhost:5000/dashboard
```

## Usage

1. Click "Upload Identifying Information" button
2. Drag and drop PDF files or click to browse
3. The system will:
   - Extract text from PDFs using Gemini OCR
   - Structure the extracted data according to your dataset format
   - Display the results in a table format

## API Endpoints

- `POST /api/upload-pdf` - Upload and process a single PDF
- `POST /api/process-multiple-pdfs` - Upload and process multiple PDFs

## Notes

- PDF files are temporarily stored during processing
- The system uses Gemini 1.5 Pro for OCR and data structuring
- Make sure your dataset file (`topo/global_dataset.xlsx`) exists for proper column mapping

