"""Tests for the Google Fonts runtime sanitizer in the dashboard."""

from src.dashboard.app import _safe_html


class TestSafeHtml:
    """Verify _safe_html strips Google Fonts @import at runtime."""

    def test_strips_google_fonts_import(self):
        css = (
            '<style>'
            '@import url("https://fonts.googleapis.com/css2?family=Inter");'
            'body { color: red; }'
            '</style>'
        )
        result = _safe_html(css)
        assert "googleapis" not in result
        assert "body { color: red; }" in result

    def test_strips_single_quoted_import(self):
        css = "@import url('https://fonts.googleapis.com/css?family=Roboto');"
        result = _safe_html(css)
        assert "googleapis" not in result

    def test_strips_no_quote_import(self):
        css = "@import url(https://fonts.googleapis.com/css2?family=JetBrains+Mono);"
        result = _safe_html(css)
        assert "googleapis" not in result

    def test_preserves_normal_css(self):
        css = (
            "<style>"
            ".stApp { background: #0a0e17; }"
            "h1 { font-family: Inter, sans-serif; }"
            "</style>"
        )
        assert _safe_html(css) == css

    def test_strips_multiple_imports(self):
        css = (
            '@import url("https://fonts.googleapis.com/css2?family=Inter");'
            '@import url("https://fonts.googleapis.com/css2?family=Roboto");'
            'body { color: red; }'
        )
        result = _safe_html(css)
        assert "googleapis" not in result
        assert result.count("external font blocked") == 2
        assert "body { color: red; }" in result

    def test_case_insensitive(self):
        css = '@import url("https://FONTS.GOOGLEAPIS.COM/css2?family=Inter");'
        result = _safe_html(css)
        assert "GOOGLEAPIS" not in result

    def test_leaves_comment_as_breadcrumb(self):
        css = '@import url("https://fonts.googleapis.com/css2?family=Inter");'
        result = _safe_html(css)
        assert "/* [ATM] external font blocked" in result
