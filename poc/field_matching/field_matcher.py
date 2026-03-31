"""
Field Name Matching Proof-of-Concept

Proves that fuzzy string matching can reliably map LLM-extracted
field names to actual PDF form annotation names, replacing the
fragile positional mapping approach.

Usage:
    python field_matcher.py
"""

import os
import json
import logging
from datetime import datetime
from difflib import SequenceMatcher
from typing import Optional
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from common import save_json_to_results

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


class FieldMatcher:
    """Matches LLM-extracted field names to PDF annotation names."""

    def __init__(self, threshold: float = 0.6):
        self.threshold = threshold
        logger.info(f"FieldMatcher initialized with threshold: {threshold}")

    def extract_pdf_field_names(self, pdf_path: str) -> list:
        """Extract all annotation field names from a PDF.
        
        Uses pdfrw to read the PDF, iterates through pages and 
        annotations to collect field names from /T attributes.
        Falls back to pypdf if pdfrw fails.
        
        Args:
            pdf_path: Path to the PDF file
            
        Returns:
            list: List of field name strings
        """
        field_names = []
        
        # Try pdfrw first
        try:
            from pdfrw import PdfReader
            logger.info(f"Reading PDF with pdfrw: {pdf_path}")
            
            reader = PdfReader(pdf_path)
            
            for page_num, page in enumerate(reader.pages):
                if page.Annots:
                    for annot in page.Annots:
                        if annot.Subtype == "/Widget" and annot.T:
                            # Remove the parentheses from field name
                            field_name = str(annot.T).strip("()")
                            field_names.append(field_name)
                            logger.debug(f"Found field: {field_name}")
            
            if field_names:
                logger.info(f"pdfrw: Found {len(field_names)} fields")
                return field_names
        except Exception as e:
            logger.warning(f"pdfrw failed: {e}")
        
        # Try pypdf as fallback
        try:
            from pypdf import PdfReader
            logger.info(f"Reading PDF with pypdf: {pdf_path}")
            
            reader = PdfReader(pdf_path)
            fields = reader.get_fields()
            
            if fields:
                field_names = list(fields.keys())
                logger.info(f"pypdf: Found {len(field_names)} fields")
                return field_names
        except Exception as e:
            logger.warning(f"pypdf failed: {e}")
        
        logger.warning("No fields found in PDF")
        return []

    def find_best_match(
        self,
        extracted_name: str,
        pdf_field_names: list
    ) -> Optional[dict]:
        """Find the best matching PDF field for an extracted name.
        
        Strategy:
        1. First try exact match (case-insensitive)
        2. If no exact match, use fuzzy matching
        3. Return None if best score < threshold
        
        Args:
            extracted_name: Name extracted from LLM
            pdf_field_names: List of PDF field names to match against
            
        Returns:
            dict with pdf_field, score, method; or None if no match above threshold
        """
        if not extracted_name or not pdf_field_names:
            logger.warning("Empty extracted name or PDF field list")
            return None
        
        # Step 1: Try exact match (case-insensitive)
        extracted_lower = extracted_name.lower()
        for pdf_field in pdf_field_names:
            if pdf_field.lower() == extracted_lower:
                logger.info(f"Exact match found: '{extracted_name}' -> '{pdf_field}'")
                return {
                    "pdf_field": pdf_field,
                    "score": 1.0,
                    "method": "exact"
                }
        
        # Step 2: Fuzzy matching
        best_score = 0
        best_match = None
        
        for pdf_field in pdf_field_names:
            score = SequenceMatcher(
                None,
                extracted_lower,
                pdf_field.lower()
            ).ratio()
            
            if score > best_score:
                best_score = score
                best_match = pdf_field
        
        # Check threshold
        if best_score >= self.threshold:
            logger.info(
                f"Fuzzy match found: '{extracted_name}' -> '{best_match}' "
                f"(score: {best_score:.3f})"
            )
            return {
                "pdf_field": best_match,
                "score": best_score,
                "method": "fuzzy"
            }
        else:
            logger.info(
                f"No match above threshold for '{extracted_name}' "
                f"(best: '{best_match}' at {best_score:.3f})"
            )
            return None

    def match_all_fields(
        self,
        extracted_names: list,
        pdf_field_names: list
    ) -> list:
        """Match all extracted field names to PDF fields.
        
        Args:
            extracted_names: List of extracted field names
            pdf_field_names: List of PDF field names
            
        Returns:
            list: Results with extracted_name, pdf_field, score, method
        """
        results = []
        
        for extracted_name in extracted_names:
            result = self.find_best_match(extracted_name, pdf_field_names)
            
            if result is None:
                results.append({
                    "extracted_name": extracted_name,
                    "pdf_field": None,
                    "score": 0.0,
                    "method": "none"
                })
            else:
                results.append({
                    "extracted_name": extracted_name,
                    "pdf_field": result["pdf_field"],
                    "score": result["score"],
                    "method": result["method"]
                })
        
        return results

    def print_results_table(self, results: list):
        """Print a formatted table of matching results.
        
        Args:
            results: List of match results
        """
        print("\n" + "-" * 120)
        print(f"{'Extracted Name':<35} {'Best PDF Match':<35} {'Score':<15} {'Status':<10}")
        print("-" * 120)
        
        matches = 0
        for result in results:
            extracted = result["extracted_name"]
            pdf_field = result["pdf_field"] or "NONE"
            score = result["score"]
            status = "[MATCH]" if result["pdf_field"] else "[NO MATCH]"
            
            if result["pdf_field"]:
                matches += 1
            
            print(f"{extracted:<35} {pdf_field:<35} {score:<15.3f} {status:<10}")
        
        print("-" * 120)
        print(f"Summary: Matched {matches}/{len(results)} fields")
        print()


# Test scenarios
SCENARIO_CLEAN = {
    "name": "Clean Field Names",
    "extracted_names": [
        "Employee's name",
        "Employee's job title",
        "Employee's department supervisor",
        "Employee's phone number",
        "Employee's email",
        "Signature",
        "Date"
    ]
}

SCENARIO_ABBREVIATED = {
    "name": "Abbreviated / Informal Names",
    "extracted_names": [
        "name",
        "title",
        "supervisor",
        "phone",
        "email",
        "sig",
        "date"
    ]
}

SCENARIO_LLM_STYLE = {
    "name": "LLM-Generated Names (Realistic)",
    "extracted_names": [
        "employee_name",
        "job_title",
        "department_supervisor",
        "phone_number",
        "email_address",
        "signature",
        "date"
    ]
}

SCENARIO_OPAQUE = {
    "name": "Opaque Agency Identifiers (Should NOT Match)",
    "extracted_names": [
        "Street Address",
        "Incident Number",
        "Officer Badge",
        "Fire Cause"
    ],
    "override_pdf_fields": [
        "NFIRS_Blk_C_1",
        "NFIRS_Inc_No",
        "NFIRS_Off_Badge",
        "NFIRS_Cause_Code"
    ]
}


if __name__ == "__main__":
    print("\n" + "=" * 120)
    print("FireForm PoC: Field Name Matching")
    print("=" * 120)

    # Read actual PDF fields from the sample form
    pdf_path = Path(__file__).parent.parent.parent / "src" / "inputs" / "file.pdf"

    matcher = FieldMatcher(threshold=0.6)

    # Try to read fields from actual PDF
    if pdf_path.exists():
        pdf_fields = matcher.extract_pdf_field_names(str(pdf_path))
        if pdf_fields:
            print(f"\n[OK] PDF fields found: {pdf_fields}")
        else:
            print(f"\n[WARN] PDF exists but no fields extracted. Using simulated field names.")
            pdf_fields = [
                "Employee's name",
                "Employee's job title",
                "Employee's department supervisor",
                "Employee's phone number",
                "Employee's email",
                "Signature",
                "Date"
            ]
    else:
        print(f"\n[WARN] PDF not found at {pdf_path}")
        print("Using simulated PDF field names.")
        pdf_fields = [
            "Employee's name",
            "Employee's job title",
            "Employee's department supervisor",
            "Employee's phone number",
            "Employee's email",
            "Signature",
            "Date"
        ]

    # Run all scenarios
    all_results = {}

    for scenario in [SCENARIO_CLEAN, SCENARIO_ABBREVIATED,
                     SCENARIO_LLM_STYLE, SCENARIO_OPAQUE]:
        print(f"\n--- Scenario: {scenario['name']} ---")

        target_pdf_fields = scenario.get(
            "override_pdf_fields", pdf_fields
        )

        results = matcher.match_all_fields(
            scenario["extracted_names"],
            target_pdf_fields
        )
        matcher.print_results_table(results)

        all_results[scenario["name"]] = {
            "scenario": scenario["name"],
            "extracted_names": scenario["extracted_names"],
            "pdf_fields": target_pdf_fields,
            "results": results,
            "threshold": matcher.threshold
        }

    # Save all results
    filepath = save_json_to_results(all_results, "matching_results", "field_matching")
    print(f"Results saved to: {filepath}")

    print("\n" + "=" * 120)
    print("Field matching PoC complete.")
    print("=" * 120 + "\n")
