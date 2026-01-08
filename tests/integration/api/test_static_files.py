"""
Integration tests for static file serving (T181).

Tests that FastAPI correctly serves the web chat interface files.
"""
import pytest
from fastapi.testclient import TestClient


class TestStaticFileServing:
    """Test static file serving for web UI."""

    def test_serves_index_html(self, client):
        """Test that index.html is served at root."""
        response = client.get("/")
        
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/html; charset=utf-8"
        assert b"<!DOCTYPE html>" in response.content
        assert b"ContextDock" in response.content

    def test_serves_css_file(self, client):
        """Test that CSS stylesheet is served."""
        response = client.get("/styles.css")
        
        assert response.status_code == 200
        assert "text/css" in response.headers["content-type"]

    def test_serves_javascript_file(self, client):
        """Test that JavaScript client is served."""
        response = client.get("/app.js")
        
        assert response.status_code == 200
        assert "application/javascript" in response.headers["content-type"] or "text/javascript" in response.headers["content-type"]

    def test_404_for_missing_file(self, client):
        """Test that missing files return 404."""
        response = client.get("/nonexistent.html")
        
        assert response.status_code == 404

    def test_index_contains_app_structure(self, client):
        """Test that index.html contains expected app structure."""
        response = client.get("/")
        content = response.content.decode("utf-8")
        
        # Check for main app container
        assert '<div id="app"' in content or '<div class="app"' in content
        
        # Check for chat interface elements
        assert "chat" in content.lower()
        assert "message" in content.lower()

    def test_index_includes_stylesheets(self, client):
        """Test that index.html includes CSS stylesheets."""
        response = client.get("/")
        content = response.content.decode("utf-8")
        
        assert 'href="styles.css"' in content or 'href="/styles.css"' in content

    def test_index_includes_scripts(self, client):
        """Test that index.html includes JavaScript."""
        response = client.get("/")
        content = response.content.decode("utf-8")
        
        assert 'src="app.js"' in content or 'src="/app.js"' in content

    def test_html_has_proper_doctype(self, client):
        """Test that HTML has proper DOCTYPE."""
        response = client.get("/")
        content = response.content.decode("utf-8")
        
        assert content.startswith("<!DOCTYPE html>") or content.lstrip().startswith("<!DOCTYPE html>")

    def test_html_has_lang_attribute(self, client):
        """Test that HTML has language attribute for accessibility."""
        response = client.get("/")
        content = response.content.decode("utf-8")
        
        assert 'lang="en"' in content

    def test_html_has_viewport_meta(self, client):
        """Test that HTML has viewport meta tag for responsive design."""
        response = client.get("/")
        content = response.content.decode("utf-8")
        
        assert "viewport" in content
        assert "width=device-width" in content


class TestStaticFileHeaders:
    """Test HTTP headers for static files."""

    def test_html_has_utf8_charset(self, client):
        """Test that HTML is served with UTF-8 charset."""
        response = client.get("/")
        
        assert "charset=utf-8" in response.headers["content-type"].lower()

    def test_css_has_correct_content_type(self, client):
        """Test that CSS has correct content type."""
        response = client.get("/styles.css")
        
        assert response.status_code == 200
        content_type = response.headers["content-type"]
        assert "text/css" in content_type

    def test_js_has_correct_content_type(self, client):
        """Test that JavaScript has correct content type."""
        response = client.get("/app.js")
        
        assert response.status_code == 200
        content_type = response.headers["content-type"]
        assert "javascript" in content_type.lower()


class TestStaticFileCaching:
    """Test caching headers for static files."""

    def test_static_files_have_cache_headers(self, client):
        """Test that static files have appropriate cache headers."""
        response = client.get("/styles.css")
        
        # Should have some form of cache control
        assert "cache-control" in response.headers or "etag" in response.headers or "last-modified" in response.headers


class TestHTMLStructure:
    """Test HTML structure and required elements."""

    def test_html_has_title(self, client):
        """Test that HTML has a title tag."""
        response = client.get("/")
        content = response.content.decode("utf-8")
        
        assert "<title>" in content
        assert "</title>" in content

    def test_html_has_head_and_body(self, client):
        """Test that HTML has head and body sections."""
        response = client.get("/")
        content = response.content.decode("utf-8")
        
        assert "<head>" in content
        assert "</head>" in content
        assert "<body>" in content
        assert "</body>" in content

    def test_html_has_charset_meta(self, client):
        """Test that HTML has charset meta tag."""
        response = client.get("/")
        content = response.content.decode("utf-8")
        
        assert 'charset="UTF-8"' in content or 'charset="utf-8"' in content
