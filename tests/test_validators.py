import pytest
from pydantic import ValidationError

from putergenai.putergenai import (NonEmptyStr, PathStr, UrlStr, validate_path,
                                   validate_string, validate_url)


class TestValidators:
    """Test string validation functions and Pydantic models."""

    def test_validate_string_valid(self):
        """Test validate_string with valid inputs."""
        assert validate_string("hello") == "hello"
        assert validate_string("  hello  ") == "hello"  # strips whitespace
        assert validate_string("hello world") == "hello world"

    def test_validate_string_invalid(self):
        """Test validate_string with invalid inputs."""
        with pytest.raises(ValidationError):
            validate_string("")  # empty string

        with pytest.raises(ValidationError):
            validate_string("   ")  # only whitespace

        with pytest.raises(ValidationError):
            validate_string(None)

    def test_validate_path_valid(self):
        """Test validate_path with valid inputs."""
        valid_paths = [
            "file.txt",
            "folder/file.txt",
            "path/to/file.txt",
            "file-name_123.txt",
            "/absolute/path/file.txt",
            "file.with.dots.txt",
        ]
        for path in valid_paths:
            result = validate_path(path)
            assert result == path, f"Path validation failed for: {path}"

    def test_validate_path_invalid(self):
        """Test validate_path with invalid inputs."""
        invalid_paths = [
            "",  # empty
            "   ",  # whitespace only
        ]
        for path in invalid_paths:
            with pytest.raises(ValidationError):
                validate_path(path)

    def test_validate_url_valid(self):
        """Test validate_url with valid URLs."""
        valid_urls = [
            ("https://example.com", "https://example.com/"),
            ("http://example.com", "http://example.com/"),
            ("https://example.com/path", "https://example.com/path"),
            (
                "https://example.com/path?query=value",
                "https://example.com/path?query=value",
            ),
            (
                "https://example.com/path#fragment",
                "https://example.com/path#fragment",
            ),
            (
                "https://subdomain.example.com/path",
                "https://subdomain.example.com/path",
            ),
        ]
        for input_url, expected_url in valid_urls:
            result = validate_url(input_url)
            assert (
                str(result) == expected_url
            ), f"URL validation mismatch: {input_url} -> {result} (expected: {expected_url})"

    def test_validate_url_invalid(self):
        """Test validate_url with invalid URLs."""
        invalid_urls = [
            "",  # empty
            "   ",  # whitespace only
            "not-a-url",
            "ftp://example.com",  # not http/https
            "example.com",  # missing protocol
            "://example.com",  # missing protocol
            "https://",  # missing domain
        ]
        for url in invalid_urls:
            with pytest.raises(ValidationError):
                validate_url(url)

    def test_non_empty_str_model(self):
        """Test NonEmptyStr Pydantic model."""
        # Valid
        model = NonEmptyStr(value="hello")
        assert model.value == "hello"

        model = NonEmptyStr(value="  hello  ")
        assert model.value == "hello"  # strips whitespace

        # Invalid
        with pytest.raises(ValidationError):
            NonEmptyStr(value="")

        with pytest.raises(ValidationError):
            NonEmptyStr(value="   ")

    def test_path_str_model(self):
        """Test PathStr Pydantic model."""
        # Valid
        model = PathStr(value="file.txt")
        assert model.value == "file.txt"

        model = PathStr(value="path/to/file.txt")
        assert model.value == "path/to/file.txt"

        # Invalid - empty paths
        with pytest.raises(ValidationError):
            PathStr(value="")

    def test_url_str_model(self):
        """Test UrlStr Pydantic model."""
        # Valid
        model = UrlStr(value="https://example.com")
        assert str(model.value) == "https://example.com/"

        # Invalid
        with pytest.raises(ValidationError):
            UrlStr(value="not-a-url")
