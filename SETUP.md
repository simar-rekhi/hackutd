# Setup Instructions

## Prerequisites

1. Python 3.8 or higher
2. Two separate NVIDIA NIM servers:
   - **Nemotron-Parse VLM Server** (for PDF/image OCR processing)
   - **Nemotron LLM Server** (for text processing and data structuring)
3. API keys for both servers (can be the same or different)
4. Poppler installed (for PDF to image conversion):
   ```bash
   brew install poppler  # macOS
   # or
   sudo apt-get install poppler-utils  # Linux
   ```

## Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Set up your NVIDIA NIM API credentials:
   - Get your API keys from your NVIDIA NIM deployments
   - Configure **TWO SEPARATE SERVERS**:
   
   **On macOS/Linux:**
   ```bash
   # Nemotron-Parse VLM Server (for PDF/image OCR)
   export NVIDIA_NIM_VLM_API_KEY="your-vlm-api-key-here"
   export NVIDIA_NIM_VLM_BASE_URL="http://your-vlm-server:9000/v1"
   
   # Nemotron LLM Server (for text processing)
   export NVIDIA_NIM_API_KEY="your-llm-api-key-here"
   export NVIDIA_NIM_BASE_URL="http://your-llm-server:8000/v1"
   export NVIDIA_NIM_MODEL="nvidia/nvidia-nemotron-nano-9b-v2"
   ```
   
   **On Windows:**
   ```cmd
   set NVIDIA_NIM_VLM_API_KEY=your-vlm-api-key-here
   set NVIDIA_NIM_VLM_BASE_URL=http://your-vlm-server:9000/v1
   set NVIDIA_NIM_API_KEY=your-llm-api-key-here
   set NVIDIA_NIM_BASE_URL=http://your-llm-server:8000/v1
   set NVIDIA_NIM_MODEL=nvidia/nvidia-nemotron-nano-9b-v2
   ```
   
   **Or create a `.env` file** (recommended):
   ```
   # Nemotron-Parse VLM Server (separate server for PDF/image OCR)
   NVIDIA_NIM_VLM_API_KEY=your-vlm-api-key-here
   NVIDIA_NIM_VLM_BASE_URL=http://your-vlm-server:9000/v1
   
   # Nemotron LLM Server (separate server for text processing)
   NVIDIA_NIM_API_KEY=your-llm-api-key-here
   NVIDIA_NIM_BASE_URL=http://your-llm-server:8000/v1
   NVIDIA_NIM_MODEL=nvidia/nvidia-nemotron-nano-9b-v2
   ```
   
   **Note:** If `NVIDIA_NIM_VLM_API_KEY` is not set, it will fall back to `NVIDIA_NIM_API_KEY`.
   
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

- **Two Separate Servers**: The system uses two different NVIDIA NIM servers:
  - **VLM Server** (Nemotron-Parse): Handles PDF/image OCR processing
  - **LLM Server** (Nemotron 9b): Handles text processing and data structuring
- PDF files are temporarily stored during processing
- PDFs are converted to images using poppler before being sent to Nemotron-Parse
- Make sure your dataset file (`topo/global_dataset.xlsx`) exists for proper column mapping
- The default LLM model is `nvidia/nvidia-nemotron-nano-9b-v2` but can be changed via `NVIDIA_NIM_MODEL` environment variable
- The VLM model is `nvidia/nemotron-parse` (configured automatically)
- If you're using custom NIM deployments, update the respective `BASE_URL` environment variables

