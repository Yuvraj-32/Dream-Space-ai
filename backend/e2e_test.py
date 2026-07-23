import os
import time
import sys
import traceback
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def run_test():
    print("Initializing Chrome webdriver in headless mode...")
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1280,800")
    
    # Enable browser logs
    options.set_capability("goog:loggingPrefs", {"browser": "ALL"})

    service = Service(r"C:\Users\Admin\.wdm\drivers\chromedriver\win64\149.0.7827.155\chromedriver-win64\chromedriver.exe")
    driver = webdriver.Chrome(service=service, options=options)
    
    try:
        url = "http://localhost:5173"
        print(f"Navigating to {url}...")
        driver.get(url)
        
        # Verify page title
        print(f"Page title: '{driver.title}'")
        assert "DreamSpace" in driver.title, f"Unexpected title: {driver.title}"
        
        # Verify initial layout
        print("Checking initial view button states...")
        detect_btn = driver.find_element(By.ID, "btn-view-detect")
        editor_btn = driver.find_element(By.ID, "btn-view-editor")
        three_d_btn = driver.find_element(By.ID, "btn-view-3d")
        
        assert not detect_btn.is_enabled(), "Detect button should be disabled initially"
        assert not editor_btn.is_enabled(), "Editor button should be disabled initially"
        assert three_d_btn.is_enabled(), "3D button should be enabled initially"
        
        # Locate file input
        print("Locating file input...")
        file_input = driver.find_element(By.ID, "file-input")
        
        # Upload floor plan image
        img_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "67ca2328a5aebddb6989e0c8_30x40 3 Bedroom Floor Plan.jpg")
        print(f"Uploading file: {img_path}...")
        file_input.send_keys(img_path)
        
        # Wait for file upload + detection process to complete
        print("Waiting for detection to run and view to switch to editor...")
        # Since it auto-switches to the editor once detection finishes, the editor button should get the "active" class
        # Wait up to 15 seconds
        WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable((By.ID, "btn-confirm-layout"))
        )
        print("Detection finished! Found 'Confirm Layout' button.")
        
        # Verify active view is editor
        active_classes = editor_btn.get_attribute("class")
        print(f"Editor button classes: '{active_classes}'")
        assert "active" in active_classes, "Editor button should be active after detection"
        
        # Verify wall count badge is present
        wall_badge = driver.find_element(By.CLASS_NAME, "wall-count-badge")
        print(f"Wall count badge text: '{wall_badge.text}'")
        assert "walls" in wall_badge.text.lower(), f"Unexpected badge text: {wall_badge.text}"
        
        # Click "Confirm Layout" button
        confirm_btn = driver.find_element(By.ID, "btn-confirm-layout")
        print("Clicking 'Confirm Layout' button...")
        confirm_btn.click()
        
        # Wait for view to switch to 3D mode
        print("Waiting for view to switch to 3D...")
        WebDriverWait(driver, 10).until(
            lambda d: "active" in d.find_element(By.ID, "btn-view-3d").get_attribute("class")
        )
        print("View switched to 3D successfully.")
        
        # Verify Showcase button is now visible
        showcase_btn = driver.find_element(By.ID, "btn-showcase")
        assert showcase_btn.is_displayed(), "Showcase button should be visible after layout confirmation"
        print("Showcase button is visible.")
        
        # Click Showcase button
        print("Clicking 'Showcase' button...")
        showcase_btn.click()
        
        # Verify showcase hud exists
        WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CLASS_NAME, "showcase-hud"))
        )
        print("Showcase HUD is rendered.")
        
        # Click "Exit Showcase"
        exit_btn = driver.find_element(By.CLASS_NAME, "exit-btn")
        print("Clicking 'Exit Showcase'...")
        exit_btn.click()
        
        # Verify exit worked
        WebDriverWait(driver, 5).until(
            lambda d: len(d.find_elements(By.CLASS_NAME, "showcase-hud")) == 0
        )
        print("Exited showcase mode successfully.")
        
        # Retrieve and log browser console output to verify no exceptions
        print("Checking browser logs...")
        logs = driver.get_log("browser")
        
        print(f"Total browser logs: {len(logs)}")
        severe_errors = []
        for log in logs:
            print(f"[{log['level']}] {log['message']}")
            if log["level"] == "SEVERE":
                # Filter out favicon issues, external resources, or typical non-breaking stuff
                if "favicon.ico" not in log["message"]:
                    severe_errors.append(log["message"])
            
        assert len(severe_errors) == 0, f"Found browser SEVERE errors: {severe_errors}"
        print("E2E UI Test PASSED successfully! All buttons work correctly.")
        
    except Exception as e:
        print("E2E UI Test FAILED!")
        traceback.print_exc()
        try:
            driver.save_screenshot("test_failure.png")
            print("Saved failure screenshot to test_failure.png")
        except Exception as screenshot_err:
            print(f"Could not save screenshot: {screenshot_err}")
        sys.exit(1)
    finally:
        driver.quit()

if __name__ == "__main__":
    run_test()
