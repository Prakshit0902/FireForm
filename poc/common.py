"""Shared utilities for FireForm PoC modules."""

import os
import json
from datetime import datetime
from pathlib import Path


def load_ollama_host() -> str:
    """Load Ollama host URL from environment variable with fallback.
    
    Returns:
        str: Ollama host URL (e.g., 'http://localhost:11434')
    """
    host = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
    return host


def get_pdf_path() -> str:
    """Resolve path to the sample PDF form.
    
    Returns:
        str: Absolute path to src/inputs/file.pdf
        
    Raises:
        FileNotFoundError: If PDF does not exist
    """
    # Get FireForm root directory (go up from poc/ to root)
    fireform_root = Path(__file__).parent.parent
    pdf_path = fireform_root / "src" / "inputs" / "file.pdf"
    
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found at {pdf_path}")
    
    return str(pdf_path)


def save_json_to_results(data: dict, filename: str, subdir: str) -> str:
    """Save extraction results to a timestamped JSON file.
    
    Args:
        data: Dictionary to save as JSON
        filename: Base filename (without timestamp or extension)
        subdir: Subdirectory name ('batch_extraction' or 'field_matching')
        
    Returns:
        str: Path to the saved file
    """
    results_dir = Path(__file__).parent / subdir / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = results_dir / f"{filename}_{timestamp}.json"
    
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)
    
    return str(filepath)


def format_results_json(batch_data: dict, per_field_data: dict, metadata: dict = None) -> dict:
    """Format extraction results in a standardized structure.
    
    Args:
        batch_data: Results from batch extraction
        per_field_data: Results from per-field extraction
        metadata: Optional metadata about the run
        
    Returns:
        dict: Standardized results dictionary
    """
    if metadata is None:
        metadata = {}
    
    return {
        "batch": batch_data,
        "per_field": per_field_data,
        "comparison": {
            "batch_api_calls": batch_data.get("num_api_calls", 1),
            "per_field_api_calls": per_field_data.get("num_api_calls", 0),
            "batch_time_seconds": batch_data.get("time_taken", 0),
            "per_field_time_seconds": per_field_data.get("time_taken", 0),
            "speedup_factor": (per_field_data.get("time_taken", 1) / 
                             batch_data.get("time_taken", 1)) if batch_data.get("time_taken") else 0,
        },
        "metadata": {
            "timestamp": datetime.now().isoformat(),
            **metadata
        }
    }
