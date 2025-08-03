from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import pdfplumber
import re
import json
import logging
from typing import Dict, List, Any, Optional
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Health AI Labs - Blood Test Analyzer",
    description="AI-powered blood test analysis from PDF files",
    version="1.0.0"
)

# Setup templates
templates = Jinja2Templates(directory="templates")

# Load reference ranges from file
def load_reference_ranges() -> Dict[str, Dict[str, Any]]:
    """Load reference ranges from JSON file with error handling."""
    try:
        ranges_file = Path("ranges.json")
        if not ranges_file.exists():
            raise FileNotFoundError("ranges.json file not found")
        
        with open(ranges_file) as f:
            reference_ranges = json.load(f)
            
        logger.info(f"Loaded {len(reference_ranges)} reference ranges")
        return reference_ranges
    except (json.JSONDecodeError, FileNotFoundError) as e:
        logger.error(f"Error loading reference ranges: {e}")
        raise HTTPException(status_code=500, detail="Failed to load reference ranges")

reference_ranges = load_reference_ranges()

# Extract text from uploaded PDF
def extract_text_from_pdf(file) -> str:
    """Extract text from PDF file with error handling."""
    try:
        text = ""
        with pdfplumber.open(file) as pdf:
            if not pdf.pages:
                raise ValueError("PDF has no pages")
            
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        
        if not text.strip():
            raise ValueError("No text could be extracted from PDF")
            
        logger.info(f"Successfully extracted {len(text)} characters from PDF")
        return text
    except Exception as e:
        logger.error(f"Error extracting text from PDF: {e}")
        raise HTTPException(status_code=400, detail=f"Failed to extract text from PDF: {str(e)}")

def get_status_message(test: str, value: float, ref: Dict[str, Any]) -> str:
    """Generate detailed status message for test result."""
    if value < ref["low"]:
        return f"Low – Below normal range. Consider consulting with a healthcare provider."
    elif value > ref["high"]:
        return f"High – Above normal range. You may want to adjust your lifestyle or follow up with a test."
    else:
        return "Normal – Within healthy range."

def parse_test_value(text: str, test_name: str) -> Optional[float]:
    """Parse test value from text using multiple regex patterns."""
    patterns = [
        rf"{re.escape(test_name)}\s*:?\s*(\d+\.?\d*)",  # Basic pattern with colon
        rf"{re.escape(test_name)}\s+(\d+\.?\d*)",       # Space separated
        rf"{re.escape(test_name)}.*?(\d+\.?\d*)",        # Original pattern
        rf"(?i){re.escape(test_name)}\s*[:\-=]?\s*(\d+\.?\d*)",  # Case insensitive with separators
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                continue
    return None

# Parse blood results from text
def parse_blood_tests(text: str) -> List[Dict[str, Any]]:
    """Parse blood test results from extracted text."""
    if not text.strip():
        raise ValueError("No text provided for parsing")
    
    results = []
    found_tests = 0
    
    for test, ref in reference_ranges.items():
        try:
            value = parse_test_value(text, test)
            if value is not None:
                found_tests += 1
                status = "Normal"
                
                if value < ref["low"]:
                    status = "Low"
                elif value > ref["high"]:
                    status = "High"
                
                results.append({
                    "test": test,
                    "value": value,
                    "unit": ref["unit"],
                    "range": f"{ref['low']} - {ref['high']} {ref['unit']}",
                    "status": get_status_message(test, value, ref),
                    "status_short": status
                })
            else:
                logger.warning(f"Could not find value for test: {test}")
        except Exception as e:
            logger.error(f"Error parsing test {test}: {e}")
            continue
    
    logger.info(f"Successfully parsed {found_tests} out of {len(reference_ranges)} tests")
    
    if found_tests == 0:
        raise ValueError("No blood test values could be extracted from the document")
    
    return results

def generate_summary_message(results: List[Dict[str, Any]]) -> str:
    """Generate a summary message based on test results."""
    high_count = sum(1 for r in results if r["status_short"] == "High")
    low_count = sum(1 for r in results if r["status_short"] == "Low")
    
    if high_count > 0 or low_count > 0:
        abnormal_msg = []
        if high_count > 0:
            abnormal_msg.append(f"{high_count} result(s) above normal range")
        if low_count > 0:
            abnormal_msg.append(f"{low_count} result(s) below normal range")
        
        return f"⚠️ {' and '.join(abnormal_msg)}. Consider consulting with a healthcare provider for interpretation."
    else:
        return "✅ All test results are within normal ranges."

# API routes
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Serve the main web interface."""
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/health")
async def health_check():
    """API health check endpoint."""
    return {"message": "Health AI Labs - Blood Test Analyzer API", "status": "running"}

@app.get("/api/tests")
async def get_available_tests():
    """Get list of available blood tests that can be analyzed."""
    return {
        "available_tests": list(reference_ranges.keys()),
        "total_tests": len(reference_ranges)
    }

@app.post("/analyze")
async def analyze_pdf(file: UploadFile = File(...)):
    """
    Analyze blood test results from an uploaded PDF file.
    
    Returns:
        JSON response with analyzed results and summary
    """
    # Validate file type
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")
    
    if file.size and file.size > 10 * 1024 * 1024:  # 10MB limit
        raise HTTPException(status_code=400, detail="File size too large. Maximum 10MB allowed.")
    
    try:
        logger.info(f"Processing file: {file.filename}")
        
        # Extract text from PDF
        content = extract_text_from_pdf(file.file)
        
        # Parse blood test results
        results = parse_blood_tests(content)
        
        # Generate summary
        summary_message = generate_summary_message(results)
        
        response = {
            "message": summary_message,
            "total_tests_found": len(results),
            "total_tests_available": len(reference_ranges),
            "results": results,
            "filename": file.filename
        }
        
        logger.info(f"Successfully analyzed {file.filename}: {len(results)} tests found")
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error analyzing PDF: {e}")
        raise HTTPException(status_code=500, detail="Internal server error occurred during analysis")

@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """Global exception handler."""
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected error occurred"}
    )
