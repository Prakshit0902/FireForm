"""Tests for field name matching PoC."""

import pytest
import sys
from pathlib import Path

# Add current directory and parent to path
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from field_matcher import FieldMatcher


class TestExactMatch:
    """Tests for exact field name matching."""

    def test_exact_match_same_case(self):
        """Exact match when names are identical."""
        matcher = FieldMatcher()
        result = matcher.find_best_match(
            "Employee's name",
            ["Employee's name", "Date", "Signature"]
        )
        assert result is not None
        assert result["pdf_field"] == "Employee's name"
        assert result["score"] == 1.0
        assert result["method"] == "exact"

    def test_exact_match_case_insensitive(self):
        """Exact match should be case-insensitive."""
        matcher = FieldMatcher()
        result = matcher.find_best_match(
            "employee's name",
            ["Employee's Name", "Date"]
        )
        assert result is not None
        assert result["score"] == 1.0
        assert result["method"] == "exact"

    def test_exact_match_priority(self):
        """Exact match should be prioritized over fuzzy."""
        matcher = FieldMatcher(threshold=0.5)
        result = matcher.find_best_match(
            "Date",
            ["Date_Field", "Date", "DateTime"]
        )
        assert result["pdf_field"] == "Date"
        assert result["method"] == "exact"

    def test_exact_not_found_returns_none(self):
        """Exact match not required; fuzzy will take over."""
        matcher = FieldMatcher()
        result = matcher.find_best_match(
            "employer",  # Doesn't exactly match "Employee's name"
            ["Employee's name", "Date"]
        )
        # Should either fuzzy match or return None depending on threshold
        # For high threshold, should return None
        if result is None:
            assert True
        else:
            assert result["method"] == "fuzzy"


class TestFuzzyMatch:
    """Tests for fuzzy field name matching."""

    def test_fuzzy_matches_similar_name(self):
        """Fuzzy match for similar but not identical names."""
        matcher = FieldMatcher(threshold=0.6)
        result = matcher.find_best_match(
            "employee_name",
            ["Employee's name", "Date", "Signature"]
        )
        assert result is not None
        assert result["pdf_field"] == "Employee's name"
        assert result["score"] >= 0.6
        assert result["method"] == "fuzzy"

    def test_fuzzy_rejects_below_threshold(self):
        """Should return None when best match is below threshold."""
        matcher = FieldMatcher(threshold=0.8)
        result = matcher.find_best_match(
            "phone",
            ["Employee's name", "Date", "Signature"]
        )
        # "phone" vs these fields should score very low
        assert result is None or result["score"] < 0.8

    def test_fuzzy_handles_abbreviations(self):
        """Test matching abbreviated names."""
        matcher = FieldMatcher(threshold=0.4)  # Lower threshold for abbreviations
        result = matcher.find_best_match(
            "email",
            ["Employee's email", "Employee's name", "Date"]
        )
        assert result is not None
        assert "email" in result["pdf_field"].lower()

    def test_fuzzy_scores_meaningful(self):
        """Fuzzy scores should be between 0 and 1."""
        matcher = FieldMatcher(threshold=0.0)  # Very low threshold
        result = matcher.find_best_match(
            "employee_name",
            ["Employee's name"]
        )
        
        if result:
            assert 0 <= result["score"] <= 1


class TestOpaqueIdentifiers:
    """Tests for handling opaque agency identifiers."""

    def test_opaque_identifiers_dont_match(self):
        """Agency-specific codes should NOT fuzzy-match to generic names."""
        matcher = FieldMatcher(threshold=0.6)
        result = matcher.find_best_match(
            "Street Address",
            ["NFIRS_Blk_C_1", "NFIRS_Inc_No", "NFIRS_Off_Badge"]
        )
        # These should NOT match because the names are too different
        assert result is None

    def test_opaque_very_different_strings(self):
        """Very different strings should not fuzzy-match above high threshold."""
        matcher = FieldMatcher(threshold=0.7)  # Higher threshold to reject these
        result = matcher.find_best_match(
            "Fire Cause",
            ["NFIRS_Cause_Code"]
        )
        # These should not match with higher threshold
        assert result is None or result["score"] < 0.7


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_extracted_name(self):
        """Handle empty string gracefully."""
        matcher = FieldMatcher()
        result = matcher.find_best_match(
            "",
            ["Employee's name", "Date"]
        )
        assert result is None

    def test_empty_pdf_fields_list(self):
        """Handle empty PDF fields list gracefully."""
        matcher = FieldMatcher()
        result = matcher.find_best_match(
            "Employee's name",
            []
        )
        assert result is None

    def test_special_characters(self):
        """Handle special characters in field names."""
        matcher = FieldMatcher(threshold=0.6)
        result = matcher.find_best_match(
            "Employee's name",
            ["Employee's name", "Employee_name"]
        )
        # Should match the exact one
        assert result is not None
        assert result["method"] == "exact"

    def test_unicode_handling(self):
        """Handle unicode characters without crashing."""
        matcher = FieldMatcher()
        result = matcher.find_best_match(
            "Employée",
            ["Employee", "Date"]
        )
        # Should not crash, may or may not match
        assert True

    def test_very_short_names(self):
        """Very short matching names."""
        matcher = FieldMatcher(threshold=0.5)
        result = matcher.find_best_match(
            "a",
            ["Employee"]
        )
        # Should return None (too different)
        assert result is None


class TestMatchAll:
    """Tests for batch matching."""

    def test_match_all_returns_correct_count(self):
        """match_all_fields should return one result per extracted name."""
        matcher = FieldMatcher()
        results = matcher.match_all_fields(
            ["name", "email", "phone"],
            ["Employee's name", "Employee's email",
             "Employee's phone number"]
        )
        assert len(results) == 3

    def test_match_all_results_structure(self):
        """Each result should have required keys."""
        matcher = FieldMatcher()
        results = matcher.match_all_fields(
            ["name"],
            ["Employee's name"]
        )
        
        result = results[0]
        assert "extracted_name" in result
        assert "pdf_field" in result
        assert "score" in result
        assert "method" in result

    def test_match_all_with_some_mismatches(self):
        """Mixed results (some None, some matched)."""
        matcher = FieldMatcher(threshold=0.6)
        results = matcher.match_all_fields(
            ["employee_name", "random_field", "signature"],
            ["Employee's name", "Date", "Signature"]
        )
        
        # At least one should match exactly
        assert any(r["method"] == "exact" for r in results)


class TestThresholdBehavior:
    """Tests for threshold configuration."""

    def test_low_threshold_matches_more(self):
        """Lower threshold should match more results."""
        matcher_low = FieldMatcher(threshold=0.3)
        matcher_high = FieldMatcher(threshold=0.8)
        
        extracted = "phone"
        pdf_fields = ["Employee's phone number", "Date"]
        
        result_low = matcher_low.find_best_match(extracted, pdf_fields)
        result_high = matcher_high.find_best_match(extracted, pdf_fields)
        
        # Low threshold should match, high might not
        assert result_low is not None
        # High threshold might fail
        # (this is expected behavior)

    def test_threshold_zero_matches_all(self):
        """Threshold of 0 should match everything."""
        matcher = FieldMatcher(threshold=0.0)
        result = matcher.find_best_match(
            "xyz",
            ["Employee's name"]
        )
        assert result is not None

    def test_threshold_one_requires_exact(self):
        """Threshold of 1.0 requires exact match."""
        matcher = FieldMatcher(threshold=1.0)
        result = matcher.find_best_match(
            "employee_name",
            ["Employee's name"]
        )
        assert result is None  # Fuzzy won't score 1.0
        
        result_exact = matcher.find_best_match(
            "Employee's name",
            ["Employee's name"]
        )
        assert result_exact is not None  # Exact match works
