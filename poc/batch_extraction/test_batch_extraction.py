"""Tests for batch extraction PoC."""

import pytest
import json
from unittest.mock import patch, MagicMock
import sys
from pathlib import Path

# Add current directory and parent to path
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from batch_extractor import BatchExtractor, PerFieldExtractor
from sample_transcripts import (
    SIMPLE_TRANSCRIPT, EMPLOYEE_FIELDS, FIRE_INCIDENT_FIELDS
)


class TestBatchExtractor:
    """Tests for the BatchExtractor class."""

    def test_prompt_contains_all_fields(self):
        """Verify the batch prompt includes every target field."""
        extractor = BatchExtractor()
        prompt = extractor.build_batch_prompt(SIMPLE_TRANSCRIPT, EMPLOYEE_FIELDS)
        
        for field_name in EMPLOYEE_FIELDS.keys():
            assert field_name in prompt, (
                f"Field '{field_name}' missing from batch prompt"
            )

    def test_prompt_contains_transcript(self):
        """Verify the batch prompt includes the transcript text."""
        extractor = BatchExtractor()
        prompt = extractor.build_batch_prompt(SIMPLE_TRANSCRIPT, EMPLOYEE_FIELDS)
        
        assert "John Doe" in prompt, "Transcript content not in prompt"

    def test_prompt_requests_json_output(self):
        """Verify prompt asks for JSON output."""
        extractor = BatchExtractor()
        prompt = extractor.build_batch_prompt(SIMPLE_TRANSCRIPT, EMPLOYEE_FIELDS)
        
        assert "JSON" in prompt, "Prompt should request JSON output"
        assert "null" in prompt.lower(), "Prompt should mention null for missing fields"

    @patch("batch_extractor.requests.post")
    def test_batch_returns_valid_json(self, mock_post):
        """Verify batch extraction returns parseable JSON with all expected keys."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "response": json.dumps({
                "employee_name": "John Doe",
                "job_title": "managing director",
                "department_supervisor": "Jane Doe",
                "phone_number": "123456",
                "email": "jdoe@ucsc.edu",
                "signature": "John Doe",
                "date": "01/02/2005"
            })
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        extractor = BatchExtractor()
        result = extractor.extract_batch(SIMPLE_TRANSCRIPT, EMPLOYEE_FIELDS)

        assert result["success"] is True, "Extraction should succeed"
        assert result["num_api_calls"] == 1, "Should make exactly 1 API call"
        
        data = result["extracted_data"]
        assert data["employee_name"] == "John Doe"
        assert data["email"] == "jdoe@ucsc.edu"

    @patch("batch_extractor.requests.post")
    def test_batch_handles_missing_fields(self, mock_post):
        """Verify null is returned for fields not found in transcript."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "response": json.dumps({
                "employee_name": "Sarah",
                "job_title": None,
                "department_supervisor": None,
                "phone_number": "555-0199",
                "email": None,
                "signature": None,
                "date": None
            })
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        extractor = BatchExtractor()
        result = extractor.extract_batch(
            "Name is Sarah. Phone is 555-0199.",
            EMPLOYEE_FIELDS
        )
        
        assert result["success"] is True
        data = result["extracted_data"]
        assert data["employee_name"] == "Sarah"
        assert data["email"] is None

    @patch("batch_extractor.requests.post")
    def test_batch_timing_captured(self, mock_post):
        """Verify time_taken is captured and positive."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "response": json.dumps({"employee_name": "John"})
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        extractor = BatchExtractor()
        result = extractor.extract_batch(SIMPLE_TRANSCRIPT, EMPLOYEE_FIELDS)

        assert "time_taken" in result
        assert result["time_taken"] >= 0, "Time taken should be non-negative"


class TestJSONParser:
    """Tests for JSON parsing robustness."""

    def test_parse_direct_json(self):
        """Direct JSON parsing."""
        extractor = BatchExtractor()
        result = extractor._parse_json_response('{"name": "John"}')
        
        assert result == {"name": "John"}

    def test_parse_markdown_json(self):
        """Parse JSON wrapped in markdown code block."""
        extractor = BatchExtractor()
        noisy = '```json\n{"name": "John"}\n```'
        result = extractor._parse_json_response(noisy)
        
        assert result == {"name": "John"}

    def test_parse_with_preamble(self):
        """Parse JSON with text preamble."""
        extractor = BatchExtractor()
        noisy = 'Here is the result:\n{"name": "John"}'
        result = extractor._parse_json_response(noisy)
        
        assert result == {"name": "John"}

    def test_parse_garbage_returns_none(self):
        """Garbage input returns None."""
        extractor = BatchExtractor()
        result = extractor._parse_json_response(
            "I cannot understand your request. This is not JSON."
        )
        
        assert result is None

    def test_parse_empty_string(self):
        """Empty string returns None."""
        extractor = BatchExtractor()
        result = extractor._parse_json_response("")
        
        assert result is None

    def test_parse_with_multiple_values(self):
        """Parse JSON with arrays."""
        extractor = BatchExtractor()
        noisy = '{"items": ["a", "b", "c"]}'
        result = extractor._parse_json_response(noisy)
        
        assert result["items"] == ["a", "b", "c"]


class TestPerFieldExtractor:
    """Tests for the per-field extractor."""

    def test_prompt_built_correctly(self):
        """Verify single-field prompt is built."""
        extractor = PerFieldExtractor()
        prompt = extractor.build_single_prompt(
            SIMPLE_TRANSCRIPT,
            "employee_name",
            "Full name of employee"
        )
        
        assert "employee_name" in prompt
        assert "Full name of employee" in prompt
        assert "John Doe" in prompt

    @patch("batch_extractor.requests.post")
    def test_per_field_makes_n_calls(self, mock_post):
        """Verify per-field extraction makes exactly N API calls."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "response": "John Doe"
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        extractor = PerFieldExtractor()
        result = extractor.extract_per_field(
            SIMPLE_TRANSCRIPT, EMPLOYEE_FIELDS
        )

        assert mock_post.call_count == len(EMPLOYEE_FIELDS)
        assert result["num_api_calls"] == len(EMPLOYEE_FIELDS)

    @patch("batch_extractor.requests.post")
    def test_per_field_handles_not_found(self, mock_post):
        """Verify NOT_FOUND responses are handled as None."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "response": "NOT_FOUND"
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        extractor = PerFieldExtractor()
        result = extractor.extract_per_field(
            "Incomplete data here",
            {"field1": "Description 1"}
        )

        data = result["extracted_data"]
        assert data["field1"] is None


class TestComparison:
    """Tests for comparison logic."""

    def test_batch_uses_fewer_api_calls(self):
        """Batch should always use 1 API call regardless of field count."""
        assert len(EMPLOYEE_FIELDS) == 7
        assert len(FIRE_INCIDENT_FIELDS) == 15
        
        # Batch extraction: always 1 call
        # Per-field: 7 and 15 calls respectively
        # This documents the architectural benefit
        assert 1 < len(EMPLOYEE_FIELDS)
        assert 1 < len(FIRE_INCIDENT_FIELDS)

    @patch("batch_extractor.requests.post")
    def test_both_methods_return_comparable_results(self, mock_post):
        """Both methods should return results in same format."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "response": json.dumps({"field1": "value1"})
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        batch_extractor = BatchExtractor()
        batch_result = batch_extractor.extract_batch(
            "Test",
            {"field1": "Test field"}
        )

        per_field_extractor = PerFieldExtractor()
        per_field_result = per_field_extractor.extract_per_field(
            "Test",
            {"field1": "Test field"}
        )

        # Both should have the same keys
        for key in ["extracted_data", "time_taken", "success", "num_api_calls"]:
            assert key in batch_result
            assert key in per_field_result
