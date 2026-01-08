"""
End-to-end test for US6 Scenario 2: Expand citation (T188).

Scenario: User clicks citation to view full details in modal

Test Steps:
1. Send query and receive answer with citations
2. Click citation or press Enter on focused citation
3. Verify modal opens with citation details
4. Verify citation content (source, excerpt, link)
5. Click close button or press Escape
6. Verify modal closes and focus returns
"""
import pytest
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time


@pytest.fixture(scope="module")
def driver():
    """Setup Selenium WebDriver."""
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    
    driver = webdriver.Chrome(options=options)
    driver.set_window_size(1920, 1080)
    
    yield driver
    
    driver.quit()


@pytest.fixture
def web_ui_url():
    """Web UI URL."""
    return "http://localhost:8000/app"


class TestUS6Scenario2:
    """Test US6 Scenario 2: Expand citation in modal."""

    def test_modal_opens_on_citation_click(self, driver, web_ui_url):
        """Test that clicking citation opens modal with details."""
        driver.get(web_ui_url)
        
        # Wait for page load
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "citation-modal"))
        )
        
        modal = driver.find_element(By.ID, "citation-modal")
        
        # Modal should be hidden initially
        assert modal.value_of_css_property("display") == "none", \
            "Modal should be hidden initially"
        
        # Simulate adding a message with citations (since we don't have backend)
        driver.execute_script("""
            const mockCitation = {
                source: "Test Source",
                author: "Test Author",
                date: "2024-01-15",
                excerpt: "This is a test citation excerpt.",
                url: "https://example.com/test"
            };
            
            window.showCitationModal(mockCitation, 1);
        """)
        
        time.sleep(0.3)
        
        # Modal should be visible
        assert modal.value_of_css_property("display") == "flex", \
            "Modal should be visible after citation click"

    def test_modal_displays_citation_details(self, driver, web_ui_url):
        """Test that modal displays complete citation details."""
        driver.get(web_ui_url)
        
        # Wait for page load
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "citation-modal"))
        )
        
        # Open modal with test citation
        driver.execute_script("""
            const mockCitation = {
                source: "API Documentation",
                author: "ContextDock Team",
                date: "2024-01-15",
                excerpt: "The ContextDock API provides endpoints for querying workspace data.",
                url: "https://docs.contextdock.io/api"
            };
            
            window.showCitationModal(mockCitation, 1);
        """)
        
        time.sleep(0.3)
        
        # Verify modal content
        modal_content = driver.find_element(By.CLASS_NAME, "modal-content")
        content_text = modal_content.text
        
        assert "API Documentation" in content_text, "Should display source"
        assert "ContextDock Team" in content_text, "Should display author"
        assert "2024-01-15" in content_text, "Should display date"
        assert "The ContextDock API provides endpoints" in content_text, \
            "Should display excerpt"

    def test_modal_has_deep_link(self, driver, web_ui_url):
        """Test that modal has clickable deep link to source."""
        driver.get(web_ui_url)
        
        # Wait for page load
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "citation-modal"))
        )
        
        # Open modal with test citation
        test_url = "https://docs.contextdock.io/api"
        driver.execute_script(f"""
            const mockCitation = {{
                source: "API Docs",
                author: "Team",
                date: "2024-01-15",
                excerpt: "Test excerpt",
                url: "{test_url}"
            }};
            
            window.showCitationModal(mockCitation, 1);
        """)
        
        time.sleep(0.3)
        
        # Find link in modal
        modal_content = driver.find_element(By.CLASS_NAME, "modal-content")
        links = modal_content.find_elements(By.TAG_NAME, "a")
        
        assert len(links) > 0, "Modal should have at least one link"
        
        # Verify link properties
        citation_link = links[0]
        assert citation_link.get_attribute("href") == test_url, \
            "Link should point to citation URL"
        assert citation_link.get_attribute("target") == "_blank", \
            "Link should open in new tab"
        assert citation_link.get_attribute("rel") == "noopener noreferrer", \
            "Link should have security attributes"

    def test_modal_closes_on_close_button(self, driver, web_ui_url):
        """Test that clicking close button closes modal."""
        driver.get(web_ui_url)
        
        # Wait for page load
        modal = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "citation-modal"))
        )
        
        # Open modal
        driver.execute_script("""
            const mockCitation = {
                source: "Test",
                author: "Test",
                date: "2024-01-15",
                excerpt: "Test",
                url: "https://example.com"
            };
            
            window.showCitationModal(mockCitation, 1);
        """)
        
        time.sleep(0.3)
        
        # Modal should be visible
        assert modal.value_of_css_property("display") == "flex", \
            "Modal should be visible"
        
        # Click close button
        close_button = driver.find_element(By.ID, "modal-close")
        close_button.click()
        
        time.sleep(0.3)
        
        # Modal should be hidden
        assert modal.value_of_css_property("display") == "none", \
            "Modal should be hidden after close"

    def test_modal_closes_on_escape_key(self, driver, web_ui_url):
        """Test that pressing Escape closes modal."""
        driver.get(web_ui_url)
        
        # Wait for page load
        modal = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "citation-modal"))
        )
        
        # Open modal
        driver.execute_script("""
            const mockCitation = {
                source: "Test",
                author: "Test",
                date: "2024-01-15",
                excerpt: "Test",
                url: "https://example.com"
            };
            
            window.showCitationModal(mockCitation, 1);
        """)
        
        time.sleep(0.3)
        
        # Modal should be visible
        assert modal.value_of_css_property("display") == "flex", \
            "Modal should be visible"
        
        # Press Escape
        body = driver.find_element(By.TAG_NAME, "body")
        body.send_keys(Keys.ESCAPE)
        
        time.sleep(0.3)
        
        # Modal should be hidden
        assert modal.value_of_css_property("display") == "none", \
            "Modal should be hidden after Escape"

    def test_modal_closes_on_backdrop_click(self, driver, web_ui_url):
        """Test that clicking modal backdrop closes modal."""
        driver.get(web_ui_url)
        
        # Wait for page load
        modal = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "citation-modal"))
        )
        
        # Open modal
        driver.execute_script("""
            const mockCitation = {
                source: "Test",
                author: "Test",
                date: "2024-01-15",
                excerpt: "Test",
                url: "https://example.com"
            };
            
            window.showCitationModal(mockCitation, 1);
        """)
        
        time.sleep(0.3)
        
        # Click modal backdrop (the modal element itself, not modal-content)
        modal.click()
        
        time.sleep(0.3)
        
        # Modal should be hidden
        assert modal.value_of_css_property("display") == "none", \
            "Modal should be hidden after backdrop click"

    def test_modal_close_button_receives_focus(self, driver, web_ui_url):
        """Test that close button receives focus when modal opens."""
        driver.get(web_ui_url)
        
        # Wait for page load
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "citation-modal"))
        )
        
        # Open modal
        driver.execute_script("""
            const mockCitation = {
                source: "Test",
                author: "Test",
                date: "2024-01-15",
                excerpt: "Test",
                url: "https://example.com"
            };
            
            window.showCitationModal(mockCitation, 1);
        """)
        
        time.sleep(0.3)
        
        # Close button should have focus
        active_element = driver.switch_to.active_element
        assert active_element.get_attribute("id") == "modal-close", \
            "Close button should have focus when modal opens"

    def test_citation_number_displayed_in_modal(self, driver, web_ui_url):
        """Test that citation number is displayed in modal header."""
        driver.get(web_ui_url)
        
        # Wait for page load
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "citation-modal"))
        )
        
        # Open modal with citation number 5
        driver.execute_script("""
            const mockCitation = {
                source: "Test Source",
                author: "Test Author",
                date: "2024-01-15",
                excerpt: "Test excerpt",
                url: "https://example.com"
            };
            
            window.showCitationModal(mockCitation, 5);
        """)
        
        time.sleep(0.3)
        
        # Find modal header
        modal_content = driver.find_element(By.CLASS_NAME, "modal-content")
        header = modal_content.find_element(By.TAG_NAME, "h2")
        
        # Should contain citation number
        assert "[5]" in header.text or "Citation 5" in header.text, \
            "Modal header should display citation number"

    def test_multiple_citations_sequential_access(self, driver, web_ui_url):
        """Test opening multiple citations sequentially."""
        driver.get(web_ui_url)
        
        # Wait for page load
        modal = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "citation-modal"))
        )
        
        # Open first citation
        driver.execute_script("""
            const citation1 = {
                source: "First Source",
                author: "Author 1",
                date: "2024-01-15",
                excerpt: "First excerpt",
                url: "https://example.com/1"
            };
            
            window.showCitationModal(citation1, 1);
        """)
        
        time.sleep(0.3)
        
        # Verify first citation
        modal_content = driver.find_element(By.CLASS_NAME, "modal-content")
        assert "First Source" in modal_content.text, "Should show first citation"
        
        # Close modal
        close_button = driver.find_element(By.ID, "modal-close")
        close_button.click()
        
        time.sleep(0.3)
        
        # Open second citation
        driver.execute_script("""
            const citation2 = {
                source: "Second Source",
                author: "Author 2",
                date: "2024-01-16",
                excerpt: "Second excerpt",
                url: "https://example.com/2"
            };
            
            window.showCitationModal(citation2, 2);
        """)
        
        time.sleep(0.3)
        
        # Verify second citation
        modal_content = driver.find_element(By.CLASS_NAME, "modal-content")
        assert "Second Source" in modal_content.text, "Should show second citation"
        assert "First Source" not in modal_content.text, \
            "Should not show previous citation"

    def test_citation_keyboard_accessible(self, driver, web_ui_url):
        """Test that citation can be opened via keyboard (Enter key)."""
        driver.get(web_ui_url)
        
        # Wait for page load
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "citation-modal"))
        )
        
        # Simulate adding a citation element with keyboard handler
        driver.execute_script("""
            const citation = document.createElement('span');
            citation.className = 'citation';
            citation.textContent = '[1]';
            citation.tabIndex = 0;
            citation.setAttribute('role', 'button');
            citation.setAttribute('aria-label', 'View citation 1');
            
            citation.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') {
                    const mockCitation = {
                        source: "Keyboard Test",
                        author: "Test",
                        date: "2024-01-15",
                        excerpt: "Keyboard access test",
                        url: "https://example.com"
                    };
                    window.showCitationModal(mockCitation, 1);
                }
            });
            
            document.getElementById('chat-messages').appendChild(citation);
        """)
        
        time.sleep(0.3)
        
        # Find and focus citation
        citation = driver.find_element(By.CLASS_NAME, "citation")
        citation.click()  # Focus it
        
        # Press Enter
        citation.send_keys(Keys.RETURN)
        
        time.sleep(0.3)
        
        # Modal should open
        modal = driver.find_element(By.ID, "citation-modal")
        assert modal.value_of_css_property("display") == "flex", \
            "Modal should open via Enter key"
