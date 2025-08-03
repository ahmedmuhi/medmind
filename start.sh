#!/bin/bash
# MedMind Startup Script
# Run this script to start your MedMind blood test analyzer

echo "🧠 Starting MedMind - AI Blood Test Analyzer"
echo "=============================================="

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "❌ Virtual environment not found!"
    echo "Please run: python -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi

# Activate virtual environment
source venv/bin/activate

# Check if required packages are installed
echo "📦 Checking dependencies..."
python -c "import fastapi, pdfplumber, sqlalchemy" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "📥 Installing missing dependencies..."
    pip install -r requirements.txt
fi

# Start the server
echo "🚀 Starting MedMind server..."
echo "   📡 Server will run on: http://localhost:8000"
echo "   🛑 Press Ctrl+C to stop"
echo ""

python main.py
