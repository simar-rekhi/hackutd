# Setup Instructions

## Prerequisites

1. Python 3.8 or higher
2. NVIDIA NIM API key and access to Nemotron models

## Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Set up your NVIDIA NIM API credentials:
   - Get your API key from [NVIDIA NIM](https://build.nvidia.com/) or your NVIDIA NIM deployment
   - Set it as an environment variable:
   
   **On macOS/Linux:**
   ```bash
   export NVIDIA_NIM_API_KEY="your-api-key-here"
   export NVIDIA_NIM_BASE_URL="https://integrate.api.nvidia.com/v1"  # Optional, defaults to this
   export NVIDIA_NIM_MODEL="meta/nemotron-4-340b-instruct"  # Optional, defaults to this
   ```
   
   **On Windows:**
   ```cmd
   set NVIDIA_NIM_API_KEY=your-api-key-here
   set NVIDIA_NIM_BASE_URL=https://integrate.api.nvidia.com/v1
   set NVIDIA_NIM_MODEL=meta/nemotron-4-340b-instruct
   ```
   
   **Or create a `.env` file** (recommended):
   ```
   NVIDIA_NIM_API_KEY=your-api-key-here
   NVIDIA_NIM_BASE_URL=https://integrate.api.nvidia.com/v1
   NVIDIA_NIM_MODEL=meta/nemotron-4-340b-instruct
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
   - Extract text from PDFs using NVIDIA Nemotron models via NIM
   - Structure the extracted data according to your dataset format
   - Display the results in a table format

## API Endpoints

- `POST /api/upload-pdf` - Upload and process a single PDF
- `POST /api/process-multiple-pdfs` - Upload and process multiple PDFs

## Notes

- PDF files are temporarily stored during processing
- The system uses NVIDIA Nemotron models via NIM for OCR and data structuring
- Make sure your dataset file (`topo/global_dataset.xlsx`) exists for proper column mapping
- The default model is `meta/nemotron-4-340b-instruct` but can be changed via `NVIDIA_NIM_MODEL` environment variable
- If you're using a custom NIM deployment, update `NVIDIA_NIM_BASE_URL` to point to your deployment endpoint

