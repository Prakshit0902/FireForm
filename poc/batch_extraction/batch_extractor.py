"""
Batch LLM Extraction Proof-of-Concept

Proves that a single Ollama API call can extract all target fields
from a transcript, replacing the current per-field loop approach.

Usage:
    python batch_extractor.py
"""

import json
import time
import logging
import requests
import os
from datetime import datetime
from typing import Optional
import sys
from pathlib import Path

# Add parent directories to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from sample_transcripts import (
    SIMPLE_TRANSCRIPT, COMPLEX_TRANSCRIPT,
    AMBIGUOUS_TRANSCRIPT, FIRE_INCIDENT_TRANSCRIPT,
    EMPLOYEE_FIELDS, FIRE_INCIDENT_FIELDS
)
from common import load_ollama_host, save_json_to_results, format_results_json

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

OLLAMA_HOST = load_ollama_host()
OLLAMA_URL = f"{OLLAMA_HOST}/api/generate"
MODEL = "mistral"
BATCH_TIMEOUT_SECONDS = int(os.getenv("BATCH_TIMEOUT_SECONDS", "180"))
PER_FIELD_TIMEOUT_SECONDS = int(os.getenv("PER_FIELD_TIMEOUT_SECONDS", "45"))


class BatchExtractor:
    """Extracts all fields in a single LLM call."""

    def __init__(self, model: str = MODEL, timeout_seconds: int = BATCH_TIMEOUT_SECONDS):
        self.model = model
        self.timeout_seconds = timeout_seconds
        logger.info(f"BatchExtractor initialized with model: {model}")

    def warmup_model(self) -> bool:
        """Warm up model to reduce first-request timeout risk."""
        payload = {
            "model": self.model,
            "prompt": "Reply with OK.",
            "stream": False,
        }
        try:
            logger.info("Warming up model before batch extraction")
            response = requests.post(
                OLLAMA_URL,
                json=payload,
                timeout=min(30, self.timeout_seconds)
            )
            response.raise_for_status()
            return True
        except Exception as e:
            logger.warning(f"Warm-up skipped due to error: {e}")
            return False

    def build_batch_prompt(self, transcript: str, fields: dict) -> str:
        """Build a single prompt that extracts ALL fields at once.
        
        Args:
            transcript: The incident transcript/description
            fields: Dict of {field_name: field_description}
            
        Returns:
            str: The complete prompt for the LLM
        """
        fields_spec = "\n".join(
            f"  - {field_name}: {description}"
            for field_name, description in fields.items()
        )
        
        prompt = f"""You are a data extraction expert. Your task is to extract specific information from the provided transcript and return ONLY valid JSON.

TARGET FIELDS TO EXTRACT:
{fields_spec}

TRANSCRIPT:
{transcript}

INSTRUCTIONS:
1. Extract information for each target field from the transcript
2. Return ONLY valid JSON with field names as keys
3. If a field is not found, use null for that field
4. Return a single best scalar value per field (string/number/null). Do not return arrays.
5. Do NOT include any explanation, markdown, or extra text
6. The JSON must be valid and parseable

Return the JSON now:
"""
        return prompt

    def extract_batch(self, transcript: str, fields: dict) -> dict:
        """Send a single API call to Ollama, parse JSON response.
        
        Args:
            transcript: The incident transcript
            fields: Dict of target fields
            
        Returns:
            dict: Result with keys: extracted_data, time_taken, raw_response, success, num_api_calls
        """
        logger.info(f"Starting batch extraction with {len(fields)} fields")
        
        prompt = self.build_batch_prompt(transcript, fields)
        logger.debug(f"Batch prompt length: {len(prompt)} chars")
        
        try:
            start_time = time.time()
            
            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "format": "json"
            }
            
            logger.info(f"Sending request to Ollama at {OLLAMA_URL}")
            response = requests.post(
                OLLAMA_URL,
                json=payload,
                timeout=self.timeout_seconds
            )
            response.raise_for_status()
            
            elapsed_time = time.time() - start_time
            json_response = response.json()
            raw_response = json_response.get("response", "")
            
            logger.info(f"Response received in {elapsed_time:.2f}s, length: {len(raw_response)} chars")
            logger.debug(f"Raw response preview: {raw_response[:200]}")
            
            extracted_data = self._parse_json_response(raw_response)
            
            if extracted_data is None:
                logger.warning("Failed to parse JSON from response")
                return {
                    "extracted_data": {},
                    "time_taken": elapsed_time,
                    "raw_response": raw_response,
                    "success": False,
                    "num_api_calls": 1,
                    "error": "JSON parsing failed"
                }
            
            extracted_data = self._normalize_extracted_data(extracted_data, fields)
            logger.info(f"Successfully extracted {len(extracted_data)} fields")
            return {
                "extracted_data": extracted_data,
                "time_taken": elapsed_time,
                "raw_response": raw_response,
                "success": True,
                "num_api_calls": 1
            }
            
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Connection error: {e}")
            return {
                "extracted_data": {},
                "time_taken": 0,
                "raw_response": "",
                "success": False,
                "num_api_calls": 1,
                "error": f"Connection error: {e}"
            }
        except Exception as e:
            logger.error(f"Error during batch extraction: {e}")
            return {
                "extracted_data": {},
                "time_taken": 0,
                "raw_response": "",
                "success": False,
                "num_api_calls": 1,
                "error": str(e)
            }

    def _parse_json_response(self, raw_response: str) -> Optional[dict]:
        """Attempt to parse JSON from LLM response.
        
        Strategy:
        1. Try direct json.loads()
        2. If fails, try to find JSON block using regex
        3. If fails, return None
        
        Args:
            raw_response: Raw string response from LLM
            
        Returns:
            dict or None: Parsed JSON or None if parsing failed
        """
        import re
        
        # Strategy 1: Try direct parsing
        try:
            logger.debug("Attempting direct JSON parse")
            data = json.loads(raw_response)
            logger.info("Direct JSON parse succeeded")
            return data
        except json.JSONDecodeError:
            logger.debug("Direct JSON parse failed")
        
        # Strategy 2: Try to extract JSON from markdown code block
        md_pattern = r"```(?:json)?\s*\n?(.*?)\n?```"
        md_match = re.search(md_pattern, raw_response, re.DOTALL)
        if md_match:
            try:
                logger.debug("Attempting JSON parse from markdown block")
                json_str = md_match.group(1)
                data = json.loads(json_str)
                logger.info("JSON parse from markdown block succeeded")
                return data
            except json.JSONDecodeError:
                logger.debug("JSON parse from markdown block failed")
        
        # Strategy 3: Try to extract JSON object from text
        json_pattern = r"\{.*\}"
        json_match = re.search(json_pattern, raw_response, re.DOTALL)
        if json_match:
            try:
                logger.debug("Attempting JSON parse from extracted object")
                json_str = json_match.group(0)
                data = json.loads(json_str)
                logger.info("JSON parse from extracted object succeeded")
                return data
            except json.JSONDecodeError:
                logger.debug("JSON parse from extracted object failed")
        
        logger.error("All JSON parsing strategies failed")
        return None

    def _normalize_extracted_data(self, extracted_data: dict, fields: dict) -> dict:
        """Normalize model output to expected key/value shape.

        - Ensures all expected fields are present.
        - Converts single-item arrays to scalar values.
        - Converts NOT_FOUND-style strings to None.
        """
        normalized = {}

        for field_name in fields.keys():
            value = extracted_data.get(field_name)

            if isinstance(value, list):
                if len(value) == 0:
                    value = None
                elif len(value) == 1:
                    value = value[0]

            if isinstance(value, str):
                cleaned = value.strip()
                if cleaned.upper().startswith("NOT_FOUND"):
                    value = None
                else:
                    value = cleaned

            normalized[field_name] = value

        return normalized


class PerFieldExtractor:
    """Replicates the current per-field approach for comparison."""

    def __init__(self, model: str = MODEL, timeout_seconds: int = PER_FIELD_TIMEOUT_SECONDS):
        self.model = model
        self.timeout_seconds = timeout_seconds
        logger.info(f"PerFieldExtractor initialized with model: {model}")

    def build_single_prompt(self, transcript: str, field_name: str, field_description: str) -> str:
        """Build a prompt for a single field (mimics current llm.py approach).
        
        Args:
            transcript: The incident transcript
            field_name: Name of the field to extract
            field_description: Description of what to extract
            
        Returns:
            str: The prompt for a single field
        """
        prompt = f"""You are a data extraction expert. Extract the following information from the transcript:

Field: {field_name}
Description: {field_description}

Transcript:
{transcript}

Extract only the {field_name} value. If not found, respond with 'NOT_FOUND'. 
Be concise and return only the value without explanation."""
        
        return prompt

    def extract_per_field(self, transcript: str, fields: dict) -> dict:
        """Extract fields one at a time (N API calls).
        
        Args:
            transcript: The incident transcript
            fields: Dict of target fields
            
        Returns:
            dict: Result with extracted_data, time_taken, num_api_calls, etc.
        """
        num_fields = len(fields)
        logger.info(f"Starting per-field extraction with {num_fields} fields")
        
        extracted_data = {}
        raw_responses = []
        start_time = time.time()
        
        try:
            for i, (field_name, field_description) in enumerate(fields.items(), 1):
                logger.info(f"Extracting field {i}/{num_fields}: {field_name}")
                
                prompt = self.build_single_prompt(transcript, field_name, field_description)
                
                try:
                    payload = {
                        "model": self.model,
                        "prompt": prompt,
                        "stream": False
                    }
                    
                    response = requests.post(
                        OLLAMA_URL,
                        json=payload,
                        timeout=self.timeout_seconds
                    )
                    response.raise_for_status()
                    
                    json_response = response.json()
                    raw_text = json_response.get("response", "").strip()
                    raw_responses.append(raw_text)
                    
                    # Parse the response
                    if raw_text.upper() == "NOT_FOUND":
                        extracted_data[field_name] = None
                    else:
                        # Clean up the response
                        value = raw_text.strip().replace('"', '')
                        extracted_data[field_name] = value if value else None
                    
                    logger.debug(f"Field {field_name}: {extracted_data[field_name]}")
                    
                except Exception as e:
                    logger.error(f"Error extracting field {field_name}: {e}")
                    extracted_data[field_name] = None
            
            elapsed_time = time.time() - start_time
            logger.info(f"Per-field extraction completed in {elapsed_time:.2f}s")
            
            return {
                "extracted_data": extracted_data,
                "time_taken": elapsed_time,
                "raw_responses": raw_responses,
                "num_api_calls": num_fields,
                "success": True
            }
            
        except Exception as e:
            logger.error(f"Error during per-field extraction: {e}")
            elapsed_time = time.time() - start_time
            return {
                "extracted_data": extracted_data,
                "time_taken": elapsed_time,
                "raw_responses": raw_responses,
                "num_api_calls": len(extracted_data),
                "success": False,
                "error": str(e)
            }


def _is_filled_value(value) -> bool:
    """Return True if extracted value should count as filled."""
    if value is None:
        return False
    if isinstance(value, str) and value.strip() == "":
        return False
    if isinstance(value, list) and len(value) == 0:
        return False
    return True


def print_comparison_table(batch_result: dict, per_field_result: dict, test_name: str):
    """Print a formatted comparison table.
    
    Args:
        batch_result: Results from batch extraction
        per_field_result: Results from per-field extraction
        test_name: Name of the test for reference
    """
    print("\n" + "=" * 100)
    print(f"TEST: {test_name}")
    print("=" * 100)
    
    print(f"\n{'Metric':<40} {'Batch':<30} {'Per-Field':<30}")
    print("-" * 100)
    
    batch_calls = batch_result.get("num_api_calls", 0)
    per_field_calls = per_field_result.get("num_api_calls", 0)
    print(f"{'API Calls':<40} {batch_calls:<30} {per_field_calls:<30}")
    
    batch_time = batch_result.get("time_taken", 0)
    per_field_time = per_field_result.get("time_taken", 0)
    print(f"{'Time (seconds)':<40} {batch_time:<30.3f} {per_field_time:<30.3f}")
    
    if per_field_time > 0 and batch_time > 0:
        speedup = per_field_time / batch_time
        print(f"{'Speedup Factor':<40} {'1.0x (baseline)':<30} {f'{speedup:.2f}x':<30}")
    
    batch_extracted = len([
        v for v in batch_result.get("extracted_data", {}).values() if _is_filled_value(v)
    ])
    per_field_extracted = len([
        v for v in per_field_result.get("extracted_data", {}).values() if _is_filled_value(v)
    ])
    total_fields = max(
        len(batch_result.get("extracted_data", {})),
        len(per_field_result.get("extracted_data", {}))
    )
    
    print(f"{'Fields Extracted':<40} {f'{batch_extracted}/{total_fields}':<30} {f'{per_field_extracted}/{total_fields}':<30}")
    
    batch_success = batch_result.get("success", False)
    per_field_success = per_field_result.get("success", False)
    print(f"{'Success':<40} {str(batch_success):<30} {str(per_field_success):<30}")
    
    print("=" * 100)


def run_comparison(transcript: str, fields: dict, test_name: str) -> dict:
    """Run both extraction methods and compare results.
    
    Args:
        transcript: The incident transcript
        fields: Target fields dict
        test_name: Name for the test
        
    Returns:
        dict: Formatted results for saving
    """
    print(f"\n--- Running {test_name} ---")
    
    # Run batch extraction
    batch_extractor = BatchExtractor()
    batch_extractor.warmup_model()
    batch_result = batch_extractor.extract_batch(transcript, fields)

    missing_fields = []
    if batch_result.get("success"):
        batch_data = batch_result.get("extracted_data", {})
        missing_fields = [
            field_name for field_name in fields
            if not _is_filled_value(batch_data.get(field_name))
        ]
    
    # Run per-field extraction
    per_field_extractor = PerFieldExtractor()
    per_field_result = per_field_extractor.extract_per_field(transcript, fields)

    # Hybrid fallback: only fill fields that batch missed.
    hybrid_result = {
        "extracted_data": dict(batch_result.get("extracted_data", {})),
        "success": batch_result.get("success", False),
        "num_api_calls": batch_result.get("num_api_calls", 0),
        "fallback_api_calls": 0,
        "fallback_fields": [],
    }

    if not batch_result.get("success"):
        hybrid_result["extracted_data"] = dict(per_field_result.get("extracted_data", {}))
        hybrid_result["success"] = per_field_result.get("success", False)
        hybrid_result["fallback_api_calls"] = per_field_result.get("num_api_calls", 0)
        hybrid_result["fallback_fields"] = list(fields.keys())
    elif missing_fields:
        fallback_subset = {name: fields[name] for name in missing_fields}
        fallback_result = per_field_extractor.extract_per_field(transcript, fallback_subset)
        for key, value in fallback_result.get("extracted_data", {}).items():
            if _is_filled_value(value):
                hybrid_result["extracted_data"][key] = value
        hybrid_result["success"] = True
        hybrid_result["fallback_api_calls"] = fallback_result.get("num_api_calls", 0)
        hybrid_result["fallback_fields"] = missing_fields

    hybrid_result["filled_fields"] = len([
        v for v in hybrid_result.get("extracted_data", {}).values() if _is_filled_value(v)
    ])
    
    # Print comparison
    print_comparison_table(batch_result, per_field_result, test_name)
    
    # Format results
    results = format_results_json(batch_result, per_field_result, {"test_name": test_name})
    results["hybrid"] = hybrid_result
    
    return results


if __name__ == "__main__":
    print("\n" + "=" * 100)
    print("FireForm PoC: Batch vs Per-Field LLM Extraction")
    print("=" * 100)
    print(f"\nOllama Host: {OLLAMA_HOST}")
    print(f"Model: {MODEL}")

    all_results = {}

    # Test 1: Simple employee transcript
    print("\n>>> Test 1: Simple Employee Transcript")
    results_1 = run_comparison(SIMPLE_TRANSCRIPT, EMPLOYEE_FIELDS, "simple_employee")
    all_results["simple_employee"] = results_1
    filepath_1 = save_json_to_results(results_1, "simple_employee", "batch_extraction")
    print(f"Results saved to: {filepath_1}")

    # Test 2: Complex employee transcript
    print("\n>>> Test 2: Complex Employee Transcript")
    results_2 = run_comparison(COMPLEX_TRANSCRIPT, EMPLOYEE_FIELDS, "complex_employee")
    all_results["complex_employee"] = results_2
    filepath_2 = save_json_to_results(results_2, "complex_employee", "batch_extraction")
    print(f"Results saved to: {filepath_2}")

    # Test 3: Ambiguous transcript
    print("\n>>> Test 3: Ambiguous Transcript")
    results_3 = run_comparison(AMBIGUOUS_TRANSCRIPT, EMPLOYEE_FIELDS, "ambiguous")
    all_results["ambiguous"] = results_3
    filepath_3 = save_json_to_results(results_3, "ambiguous", "batch_extraction")
    print(f"Results saved to: {filepath_3}")

    # Test 4: Fire incident transcript
    print("\n>>> Test 4: Fire Incident Transcript")
    results_4 = run_comparison(FIRE_INCIDENT_TRANSCRIPT, FIRE_INCIDENT_FIELDS, "fire_incident")
    all_results["fire_incident"] = results_4
    filepath_4 = save_json_to_results(results_4, "fire_incident", "batch_extraction")
    print(f"Results saved to: {filepath_4}")

    print("\n" + "=" * 100)
    print("All tests complete. Results saved in poc/batch_extraction/results/")
    print("=" * 100 + "\n")
