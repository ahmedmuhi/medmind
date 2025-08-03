from fastapi import FastAPI, UploadFile, File, HTTPException, Request, Query, Depends
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import pdfplumber
import re
import json
import logging
from typing import Dict, List, Any, Optional
from pathlib import Path
from datetime import datetime
import hashlib
import uuid

# Import database functions
from database import (
    store_test_results, get_user_history, get_test_trends, 
    compare_latest_tests, get_user_stats, get_db, close_db
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="MedMind - AI Blood Test Analyzer",
    description="AI-powered blood test analysis from PDF files",
    version="1.0.0"
)

# Setup templates
templates = Jinja2Templates(directory="templates")

def get_user_id(request: Request) -> str:
    """
    Generate a simple user ID based on client info.
    In a real app, this would be replaced with proper authentication.
    """
    # Use IP address and User-Agent to create a simple user identifier
    client_host = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")
    
    # Create a hash for consistent user identification
    user_string = f"{client_host}:{user_agent}"
    user_id = hashlib.md5(user_string.encode()).hexdigest()[:12]
    
    return f"user_{user_id}"

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
    
    # Define specific messages for different test categories
    if test in ["Glucose", "HbA1c"]:
        if value < ref["low"]:
            return f"Low – Blood sugar is below normal. May indicate hypoglycemia or need for dietary adjustment."
        elif value > ref["high"]:
            return f"High – Blood sugar is elevated. Consider diet, exercise, and follow up with your doctor."
        else:
            return "Normal – Blood sugar levels are within healthy range."
    
    elif test in ["Total Cholesterol", "LDL", "HDL", "Triglycerides"]:
        if test == "HDL":
            if value < ref["low"]:
                return f"Low – Good cholesterol is low. Consider increasing exercise and healthy fats."
            else:
                return "Normal – Good cholesterol levels are adequate."
        elif test == "LDL":
            if value > ref["high"]:
                return f"High – Bad cholesterol is elevated. Consider diet changes and exercise."
            else:
                return "Normal – Bad cholesterol is within healthy range."
        else:
            if value < ref["low"]:
                return f"Low – Below normal range. Generally good for cardiovascular health."
            elif value > ref["high"]:
                return f"High – Elevated levels. Consider dietary changes and lifestyle modifications."
            else:
                return "Normal – Within healthy range for cardiovascular health."
    
    elif test in ["Iron", "Ferritin", "TIBC", "Transferrin Saturation"]:
        if value < ref["low"]:
            return f"Low – May indicate iron deficiency. Consider iron-rich foods or supplements."
        elif value > ref["high"]:
            return f"High – Elevated iron levels. May need further evaluation for iron overload."
        else:
            return "Normal – Iron levels are within healthy range."
    
    elif test in ["Vitamin D", "Vitamin B12", "Folate"]:
        if value < ref["low"]:
            return f"Low – Vitamin deficiency detected. Consider supplementation and dietary sources."
        elif value > ref["high"]:
            return f"High – Vitamin levels are elevated. Generally not concerning but monitor intake."
        else:
            return "Normal – Vitamin levels are adequate."
    
    elif test in ["TSH", "T3", "T4", "Free T4", "Free T3"]:
        if value < ref["low"]:
            return f"Low – May indicate hyperthyroidism. Consult with your doctor for evaluation."
        elif value > ref["high"]:
            return f"High – May indicate hypothyroidism. Follow up with healthcare provider."
        else:
            return "Normal – Thyroid function appears normal."
    
    elif test in ["ALT", "AST", "ALP", "GGT"]:
        if value < ref["low"]:
            return f"Low – Below normal range. Generally not concerning for liver function."
        elif value > ref["high"]:
            return f"High – Liver enzymes are elevated. May indicate liver stress or damage."
        else:
            return "Normal – Liver function appears normal."
    
    elif test in ["BUN", "Creatinine", "eGFR"]:
        if test == "eGFR":
            if value < ref["low"]:
                return f"Low – Kidney function may be reduced. Follow up with your doctor."
            else:
                return "Normal – Kidney function appears normal."
        else:
            if value < ref["low"]:
                return f"Low – Below normal range. Generally indicates good kidney function."
            elif value > ref["high"]:
                return f"High – May indicate reduced kidney function. Consult your healthcare provider."
            else:
                return "Normal – Kidney function markers are within healthy range."
    
    elif test in ["Hemoglobin", "Hematocrit", "RBC", "Iron", "Ferritin"]:
        if value < ref["low"]:
            return f"Low – May indicate anemia or iron deficiency. Consider iron-rich foods."
        elif value > ref["high"]:
            return f"High – Elevated levels. May need further evaluation."
        else:
            return "Normal – Blood count is within healthy range."
    
    elif test in ["WBC", "Neutrophils", "Lymphocytes"]:
        if value < ref["low"]:
            return f"Low – White blood cell count is low. May indicate infection or immune issue."
        elif value > ref["high"]:
            return f"High – White blood cell count is elevated. May indicate infection or inflammation."
        else:
            return "Normal – Immune system markers are within healthy range."
    
    else:
        # Generic message for other tests
        if value < ref["low"]:
            return f"Low – Below normal range. Consider consulting with a healthcare provider."
        elif value > ref["high"]:
            return f"High – Above normal range. You may want to follow up with your doctor."
        else:
            return "Normal – Within healthy range."

def parse_test_value(text: str, test_name: str) -> Optional[float]:
    """Parse test value from text using multiple regex patterns and common abbreviations."""
    
    # Create a mapping of test names to their common abbreviations and variants
    test_variants = {
        "Hemoglobin": ["Hemoglobin", "Hgb", "Hb", "HGB"],
        "Hematocrit": ["Hematocrit", "Hct", "HCT"],
        "RBC": ["RBC", "Red Blood Cell", "Red Blood Cells", "Erythrocytes"],
        "WBC": ["WBC", "White Blood Cell", "White Blood Cells", "Leukocytes"],
        "Platelets": ["Platelets", "PLT", "Thrombocytes"],
        "MCV": ["MCV", "Mean Corpuscular Volume"],
        "MCH": ["MCH", "Mean Corpuscular Hemoglobin"],
        "MCHC": ["MCHC", "Mean Corpuscular Hemoglobin Concentration"],
        "RDW": ["RDW", "Red Cell Distribution Width"],
        "Neutrophils": ["Neutrophils", "Neut", "PMN"],
        "Lymphocytes": ["Lymphocytes", "Lymph", "LYM"],
        "Monocytes": ["Monocytes", "Mono", "MON"],
        "Eosinophils": ["Eosinophils", "Eos", "EOS"],
        "Basophils": ["Basophils", "Baso", "BAS"],
        "Glucose": ["Glucose", "GLU", "Blood Sugar", "BS"],
        "HbA1c": ["HbA1c", "A1C", "Hemoglobin A1c", "Glycated Hemoglobin"],
        "BUN": ["BUN", "Blood Urea Nitrogen", "Urea"],
        "Creatinine": ["Creatinine", "CREAT", "Cr"],
        "eGFR": ["eGFR", "GFR", "Estimated GFR"],
        "Sodium": ["Sodium", "Na", "NA"],
        "Potassium": ["Potassium", "K", "K+"],
        "Chloride": ["Chloride", "Cl", "CL"],
        "CO2": ["CO2", "Carbon Dioxide", "Bicarbonate", "HCO3"],
        "Calcium": ["Calcium", "Ca", "CA"],
        "Phosphorus": ["Phosphorus", "Phos", "PO4", "Phosphate"],
        "Magnesium": ["Magnesium", "Mg", "MG"],
        "Total Protein": ["Total Protein", "TP", "Protein Total"],
        "Albumin": ["Albumin", "ALB", "Alb"],
        "Globulin": ["Globulin", "GLOB", "Glob"],
        "A/G Ratio": ["A/G Ratio", "Albumin Globulin Ratio", "AG Ratio"],
        "Bilirubin Total": ["Bilirubin Total", "Total Bilirubin", "T Bil", "TBIL"],
        "Bilirubin Direct": ["Bilirubin Direct", "Direct Bilirubin", "D Bil", "DBIL"],
        "ALT": ["ALT", "SGPT", "Alanine Aminotransferase"],
        "AST": ["AST", "SGOT", "Aspartate Aminotransferase"],
        "ALP": ["ALP", "Alkaline Phosphatase", "Alk Phos"],
        "GGT": ["GGT", "Gamma GT", "Gamma Glutamyl Transferase"],
        "LDH": ["LDH", "Lactate Dehydrogenase"],
        "Total Cholesterol": ["Total Cholesterol", "Cholesterol", "CHOL", "TC"],
        "HDL": ["HDL", "HDL Cholesterol", "Good Cholesterol"],
        "LDL": ["LDL", "LDL Cholesterol", "Bad Cholesterol"],
        "Triglycerides": ["Triglycerides", "TG", "TRIG"],
        "TSH": ["TSH", "Thyroid Stimulating Hormone"],
        "T3": ["T3", "Triiodothyronine", "Total T3"],
        "T4": ["T4", "Thyroxine", "Total T4"],
        "Free T4": ["Free T4", "FT4", "T4 Free"],
        "Free T3": ["Free T3", "FT3", "T3 Free"],
        "Iron": ["Iron", "Fe", "Serum Iron"],
        "Ferritin": ["Ferritin", "Ferr"],
        "TIBC": ["TIBC", "Total Iron Binding Capacity"],
        "Transferrin Saturation": ["Transferrin Saturation", "TSAT", "Iron Saturation"],
        "Vitamin D": ["Vitamin D", "25-OH Vitamin D", "25(OH)D", "Vit D"],
        "Vitamin B12": ["Vitamin B12", "B12", "Cobalamin", "Vit B12"],
        "Folate": ["Folate", "Folic Acid", "B9"],
        "CRP": ["CRP", "C-Reactive Protein", "C Reactive Protein"],
        "ESR": ["ESR", "Erythrocyte Sedimentation Rate", "Sed Rate"],
        "PSA": ["PSA", "Prostate Specific Antigen"],
        "Testosterone": ["Testosterone", "Total Testosterone", "Test"],
        "Estradiol": ["Estradiol", "E2", "Estrogen"],
        "Progesterone": ["Progesterone", "Prog"],
        "Cortisol": ["Cortisol", "Hydrocortisone"],
        "Insulin": ["Insulin", "INS"],
        "C-Peptide": ["C-Peptide", "C Peptide"],
        "Uric Acid": ["Uric Acid", "UA", "Urate"],
        "Lactate": ["Lactate", "Lactic Acid"],
        "Ammonia": ["Ammonia", "NH3"],
        "Troponin I": ["Troponin I", "TnI", "cTnI"],
        "BNP": ["BNP", "B-type Natriuretic Peptide"],
        "PT": ["PT", "Prothrombin Time"],
        "PTT": ["PTT", "Partial Thromboplastin Time", "aPTT"],
        "INR": ["INR", "International Normalized Ratio"],
        "D-Dimer": ["D-Dimer", "D Dimer"],
        "Fibrinogen": ["Fibrinogen", "Fibr"]
    }
    
    # Get all variants for the test name
    variants = test_variants.get(test_name, [test_name])
    
    # Try each variant
    for variant in variants:
        patterns = [
            rf"{re.escape(variant)}\s*:?\s*(\d+\.?\d*)",  # Basic pattern with colon
            rf"{re.escape(variant)}\s+(\d+\.?\d*)",       # Space separated
            rf"{re.escape(variant)}.*?(\d+\.?\d*)",        # Original pattern
            rf"(?i){re.escape(variant)}\s*[:\-=]?\s*(\d+\.?\d*)",  # Case insensitive with separators
            rf"(?i)\b{re.escape(variant)}\b\s*[:\-=]?\s*(\d+\.?\d*)",  # Word boundary
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
    """Health check endpoint."""
    return {"message": "MedMind - AI Blood Test Analyzer API", "status": "running"}

@app.get("/tests")
async def get_available_tests():
    """Get list of available blood tests that can be analyzed."""
    return {
        "available_tests": list(reference_ranges.keys()),
        "total_tests": len(reference_ranges)
    }

@app.post("/analyze")
async def analyze_pdf(request: Request, file: UploadFile = File(...)):
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
        
        # Get user ID
        user_id = get_user_id(request)
        
        # Extract text from PDF
        content = extract_text_from_pdf(file.file)
        
        # Parse blood test results
        results = parse_blood_tests(content)
        
        # Generate summary
        summary_message = generate_summary_message(results)
        
        # Store results in database
        db = get_db()
        try:
            session_id = store_test_results(
                user_id=user_id,
                filename=file.filename,
                results=results,
                summary_message=summary_message,
                db=db
            )
            
            # Get comparison with previous results if available
            comparison = compare_latest_tests(user_id, db)
            
            # Get user stats
            user_stats = get_user_stats(user_id, db)
            
        finally:
            close_db(db)
        
        response = {
            "message": summary_message,
            "total_tests_found": len(results),
            "total_tests_available": len(reference_ranges),
            "results": results,
            "filename": file.filename,
            "session_id": session_id,
            "comparison": comparison,
            "user_stats": user_stats,
            "timestamp": datetime.now().isoformat()
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

@app.get("/history")
async def get_history(request: Request, limit: int = Query(10, ge=1, le=50)):
    """
    Get user's test history.
    
    Args:
        limit: Maximum number of sessions to return (1-50)
    
    Returns:
        List of historical test sessions
    """
    try:
        user_id = get_user_id(request)
        
        db = get_db()
        try:
            history = get_user_history(user_id, limit, db)
            user_stats = get_user_stats(user_id, db)
        finally:
            close_db(db)
        
        return {
            "user_stats": user_stats,
            "history": history,
            "total_sessions": len(history)
        }
        
    except Exception as e:
        logger.error(f"Error getting history: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve history")

@app.get("/trends/{test_name}")
async def get_trends(request: Request, test_name: str, months: int = Query(12, ge=1, le=60)):
    """
    Get trends for a specific test over time.
    
    Args:
        test_name: Name of the blood test
        months: Number of months to analyze (1-60)
    
    Returns:
        Trend analysis for the specified test
    """
    try:
        user_id = get_user_id(request)
        
        # Validate test name
        if test_name not in reference_ranges:
            raise HTTPException(status_code=404, detail=f"Test '{test_name}' not found")
        
        db = get_db()
        try:
            trends = get_test_trends(user_id, test_name, months, db)
        finally:
            close_db(db)
        
        return trends
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting trends for {test_name}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve trends")

@app.get("/comparison")
async def get_comparison(request: Request):
    """
    Compare latest test results with previous session.
    
    Returns:
        Comparison analysis between latest two test sessions
    """
    try:
        user_id = get_user_id(request)
        
        db = get_db()
        try:
            comparison = compare_latest_tests(user_id, db)
        finally:
            close_db(db)
        
        return comparison
        
    except Exception as e:
        logger.error(f"Error getting comparison: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve comparison")

@app.get("/stats")
async def get_stats(request: Request):
    """
    Get user statistics and overall health tracking summary.
    
    Returns:
        User statistics and tracking information
    """
    try:
        user_id = get_user_id(request)
        
        db = get_db()
        try:
            stats = get_user_stats(user_id, db)
        finally:
            close_db(db)
        
        return stats
        
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve statistics")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
