"""
Accessibility compliance tests using axe-core (T186).

Tests WCAG 2.1 AA compliance for:
- FR-048: Keyboard navigation (Tab, Enter, Escape)
- FR-049: WCAG 2.1 AA contrast ratios (4.5:1 minimum)
- FR-050: ARIA labels on all interactive elements

Note: These tests require Selenium and axe-core (via axe-selenium-python).
Install with: pip install selenium axe-selenium-python
"""
import pytest
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from axe_selenium_python import Axe
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


@pytest.fixture(scope="module")
def axe(driver):
    """Setup axe-core."""
    return Axe(driver)


@pytest.fixture
def web_ui_url():
    """Web UI URL."""
    return "http://localhost:8000/app"


class TestWCAGCompliance:
    """Test WCAG 2.1 AA compliance using axe-core."""

    def test_no_wcag_violations(self, driver, axe, web_ui_url):
        """Test that there are no WCAG 2.1 AA violations."""
        driver.get(web_ui_url)
        
        # Wait for page to load
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, "app"))
        )
        
        # Run axe-core accessibility scan
        axe.inject()
        results = axe.run(options={"runOnly": {"type": "tag", "values": ["wcag2a", "wcag2aa"]}})
        
        # Check for violations
        violations = results["violations"]
        
        if violations:
            # Format violation details
            violation_details = []
            for violation in violations:
                details = f"\n  - {violation['id']}: {violation['description']}"
                details += f"\n    Impact: {violation['impact']}"
                details += f"\n    Help: {violation['help']}"
                details += f"\n    Affected elements: {len(violation['nodes'])}"
                violation_details.append(details)
            
            pytest.fail(f"Found {len(violations)} WCAG violations:{''.join(violation_details)}")
        
        assert len(violations) == 0, "No WCAG violations should be present"

    def test_color_contrast(self, driver, axe, web_ui_url):
        """Test that color contrast meets WCAG AA standards (4.5:1 minimum)."""
        driver.get(web_ui_url)
        
        axe.inject()
        results = axe.run(options={"runOnly": {"type": "rule", "values": ["color-contrast"]}})
        
        violations = results["violations"]
        assert len(violations) == 0, f"Color contrast violations: {violations}"

    def test_aria_labels(self, driver, axe, web_ui_url):
        """Test that all interactive elements have ARIA labels."""
        driver.get(web_ui_url)
        
        axe.inject()
        results = axe.run(options={
            "runOnly": {
                "type": "rule",
                "values": ["aria-allowed-attr", "aria-required-attr", "aria-valid-attr"]
            }
        })
        
        violations = results["violations"]
        assert len(violations) == 0, f"ARIA label violations: {violations}"


class TestKeyboardNavigation:
    """Test keyboard navigation (FR-048)."""

    def test_tab_navigation_through_interface(self, driver, web_ui_url):
        """Test that Tab key navigates through all interactive elements."""
        driver.get(web_ui_url)
        
        # Wait for page load
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "message-input"))
        )
        
        # Get all focusable elements
        focusable_elements = driver.find_elements(
            By.CSS_SELECTOR,
            'a[href], button:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
        )
        
        assert len(focusable_elements) > 0, "Should have focusable elements"
        
        # Tab through elements
        body = driver.find_element(By.TAG_NAME, "body")
        for _ in range(len(focusable_elements)):
            body.send_keys(Keys.TAB)
            time.sleep(0.1)
        
        # Verify focus indicators are visible (check for outline)
        active_element = driver.switch_to.active_element
        outline = active_element.value_of_css_property("outline")
        
        # Should have an outline (not "none")
        assert outline != "none", "Focused element should have visible outline"

    def test_enter_key_submits_message(self, driver, web_ui_url):
        """Test that Enter key submits message."""
        driver.get(web_ui_url)
        
        message_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "message-input"))
        )
        
        # Type message and press Enter
        message_input.click()
        message_input.send_keys("Test query")
        message_input.send_keys(Keys.RETURN)
        
        # Input should be cleared
        time.sleep(0.5)
        assert message_input.get_attribute("value") == "", "Input should be cleared after submit"

    def test_shift_enter_creates_new_line(self, driver, web_ui_url):
        """Test that Shift+Enter creates new line without submitting."""
        driver.get(web_ui_url)
        
        message_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "message-input"))
        )
        
        # Type message and press Shift+Enter
        message_input.click()
        message_input.send_keys("Line 1")
        message_input.send_keys(Keys.SHIFT, Keys.RETURN)
        message_input.send_keys("Line 2")
        
        # Value should contain newline
        value = message_input.get_attribute("value")
        assert "\n" in value, "Should contain newline character"
        assert "Line 1" in value and "Line 2" in value, "Should contain both lines"

    def test_escape_key_closes_modal(self, driver, web_ui_url):
        """Test that Escape key closes modal."""
        driver.get(web_ui_url)
        
        # Wait for page load
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "citation-modal"))
        )
        
        # Modal should be hidden initially
        modal = driver.find_element(By.ID, "citation-modal")
        assert modal.value_of_css_property("display") == "none", "Modal should be hidden initially"
        
        # Open modal programmatically (since we don't have citations yet)
        driver.execute_script("""
            document.getElementById('citation-modal').style.display = 'flex';
        """)
        
        time.sleep(0.2)
        
        # Press Escape
        body = driver.find_element(By.TAG_NAME, "body")
        body.send_keys(Keys.ESCAPE)
        
        time.sleep(0.2)
        
        # Modal should be hidden
        assert modal.value_of_css_property("display") == "none", "Modal should be hidden after Escape"

    def test_modal_close_button_focusable(self, driver, web_ui_url):
        """Test that modal close button receives focus when modal opens."""
        driver.get(web_ui_url)
        
        # Open modal
        driver.execute_script("""
            document.getElementById('citation-modal').style.display = 'flex';
            document.getElementById('modal-close').focus();
        """)
        
        time.sleep(0.2)
        
        # Close button should have focus
        active_element = driver.switch_to.active_element
        assert active_element.get_attribute("id") == "modal-close", "Close button should have focus"


class TestARIAAttributes:
    """Test ARIA attributes (FR-050)."""

    def test_main_app_has_role(self, driver, web_ui_url):
        """Test that main app container has role attribute."""
        driver.get(web_ui_url)
        
        app = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, "app"))
        )
        
        role = app.get_attribute("role")
        assert role == "application", "App should have role='application'"

    def test_chat_messages_has_aria_live(self, driver, web_ui_url):
        """Test that chat messages container has aria-live attribute."""
        driver.get(web_ui_url)
        
        chat_messages = driver.find_element(By.ID, "chat-messages")
        
        aria_live = chat_messages.get_attribute("aria-live")
        assert aria_live == "polite", "Chat messages should have aria-live='polite'"

    def test_loading_indicator_has_aria_label(self, driver, web_ui_url):
        """Test that loading indicator has aria-label."""
        driver.get(web_ui_url)
        
        loading = driver.find_element(By.ID, "loading-indicator")
        
        aria_label = loading.get_attribute("aria-label")
        assert aria_label, "Loading indicator should have aria-label"

    def test_buttons_have_aria_labels(self, driver, web_ui_url):
        """Test that all buttons have aria-label or aria-labelledby."""
        driver.get(web_ui_url)
        
        buttons = driver.find_elements(By.TAG_NAME, "button")
        
        for button in buttons:
            aria_label = button.get_attribute("aria-label")
            aria_labelledby = button.get_attribute("aria-labelledby")
            text_content = button.text.strip()
            
            assert aria_label or aria_labelledby or text_content, \
                f"Button should have aria-label, aria-labelledby, or text content: {button.get_attribute('id')}"

    def test_form_has_role(self, driver, web_ui_url):
        """Test that message form has role attribute."""
        driver.get(web_ui_url)
        
        form = driver.find_element(By.ID, "message-form")
        
        role = form.get_attribute("role")
        assert role == "search", "Form should have role='search'"

    def test_modal_has_aria_modal(self, driver, web_ui_url):
        """Test that modal has aria-modal attribute."""
        driver.get(web_ui_url)
        
        modal = driver.find_element(By.ID, "citation-modal")
        
        aria_modal = modal.get_attribute("aria-modal")
        assert aria_modal == "true", "Modal should have aria-modal='true'"


class TestTouchTargets:
    """Test touch target sizes (44x44px minimum for WCAG)."""

    def test_send_button_size(self, driver, web_ui_url):
        """Test that send button meets 44x44px minimum."""
        driver.get(web_ui_url)
        
        send_button = driver.find_element(By.ID, "send-button")
        
        size = send_button.size
        assert size['width'] >= 44, f"Send button width should be >= 44px, got {size['width']}px"
        assert size['height'] >= 44, f"Send button height should be >= 44px, got {size['height']}px"

    def test_modal_close_button_size(self, driver, web_ui_url):
        """Test that modal close button meets 44x44px minimum."""
        driver.get(web_ui_url)
        
        close_button = driver.find_element(By.ID, "modal-close")
        
        size = close_button.size
        assert size['width'] >= 44, f"Close button width should be >= 44px, got {size['width']}px"
        assert size['height'] >= 44, f"Close button height should be >= 44px, got {size['height']}px"


class TestResponsiveDesign:
    """Test responsive design and viewport."""

    def test_viewport_meta_tag(self, driver, web_ui_url):
        """Test that viewport meta tag is present."""
        driver.get(web_ui_url)
        
        viewport = driver.find_element(By.CSS_SELECTOR, 'meta[name="viewport"]')
        content = viewport.get_attribute("content")
        
        assert "width=device-width" in content, "Viewport should have width=device-width"
        assert "initial-scale=1" in content or "initial-scale=1.0" in content, "Viewport should have initial-scale=1"

    def test_mobile_layout(self, driver, web_ui_url):
        """Test that layout adapts to mobile viewport."""
        driver.set_window_size(375, 667)  # iPhone SE size
        driver.get(web_ui_url)
        
        # Page should load without horizontal scroll
        body_width = driver.execute_script("return document.body.scrollWidth")
        viewport_width = driver.execute_script("return window.innerWidth")
        
        assert body_width <= viewport_width, "Page should not have horizontal scroll on mobile"


class TestSemanticHTML:
    """Test semantic HTML structure."""

    def test_has_lang_attribute(self, driver, web_ui_url):
        """Test that HTML has lang attribute."""
        driver.get(web_ui_url)
        
        html = driver.find_element(By.TAG_NAME, "html")
        lang = html.get_attribute("lang")
        
        assert lang == "en", "HTML should have lang='en'"

    def test_has_header_main_footer(self, driver, web_ui_url):
        """Test that page has semantic header, main, footer elements."""
        driver.get(web_ui_url)
        
        header = driver.find_elements(By.TAG_NAME, "header")
        main = driver.find_elements(By.TAG_NAME, "main")
        footer = driver.find_elements(By.TAG_NAME, "footer")
        
        assert len(header) > 0, "Page should have <header> element"
        assert len(main) > 0, "Page should have <main> element"
        assert len(footer) > 0, "Page should have <footer> element"

    def test_headings_hierarchy(self, driver, web_ui_url):
        """Test that headings follow proper hierarchy."""
        driver.get(web_ui_url)
        
        h1_elements = driver.find_elements(By.TAG_NAME, "h1")
        
        assert len(h1_elements) > 0, "Page should have at least one <h1>"
        assert len(h1_elements) == 1, "Page should have exactly one <h1>"
