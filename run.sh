#!/bin/bash
# SEO Audit Pro - Start Script
echo "Starting SEO Audit Pro..."
echo "Open your browser at: http://localhost:8000"
echo ""
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
