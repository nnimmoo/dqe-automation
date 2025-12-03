import csv
import time
import os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException



HTML_FILE_PATH = os.path.abspath("report.html")
URL = f"file://{HTML_FILE_PATH}"

LOCATORS = {
    # Table Locators
    "TABLE_CONTAINER": (By.CSS_SELECTOR, "g.table"),
    "TABLE_COLUMNS": (By.CLASS_NAME, "y-column"),
    "COLUMN_HEADER_BLOCK": (By.ID, "header"),
#    "COLUMN_CELL_TEXTS": (By.CSS_SELECTOR, ".column-block[id*='cells'] .cell-text"),    
    "COLUMN_CELL_TEXTS": (By.XPATH, ".//*[contains(@id, 'cells')]//*[local-name()='text'][contains(@class, 'cell-text')]"),
    
    # Chart Locators
    "CHART_CONTAINER": (By.CLASS_NAME, "pielayer"), 
    "LEGEND_ITEMS": (By.CLASS_NAME, "legendtoggle"),   
    "CHART_SLICES": (By.CSS_SELECTOR, "g.slice"), 
    "CHART_LABELS": (By.CLASS_NAME, "chart-data-label")
}



class SeleniumDriverContext:
    """
    Context Manager to handle Selenium WebDriver initialization and teardown.
    """
    def __init__(self, headless=False):
        self.headless = headless
        self.driver = None

    def __enter__(self):
        options = webdriver.ChromeOptions()
        if self.headless:
            options.add_argument("--headless")
        options.add_argument("--start-maximized")
        # Handle local file access permissions if necessary
        options.add_argument("--allow-file-access-from-files")
        
        self.driver = webdriver.Chrome(options=options)
        return self.driver

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.driver:
            self.driver.quit()


# helper function to write CSV
def write_csv(filename, headers, data):
    """Writes a list of rows to a CSV file."""
    try:
        with open(filename, mode='w', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            if headers:
                writer.writerow(headers)
            writer.writerows(data)
        print(f"[SUCCESS] Saved data to {filename}")
    except Exception as e:
        print(f"[ERROR] Failed to write {filename}: {e}")

# Table interaction logic
def process_table(driver):
    wait = WebDriverWait(driver, 10)

    try:
        table_container = wait.until(EC.visibility_of_element_located(LOCATORS["TABLE_CONTAINER"]))
        columns = table_container.find_elements(*LOCATORS["TABLE_COLUMNS"])
        
        all_headers = []
        all_columns_data = []
        
        for col in columns:
            try:
                header_block = col.find_element(*LOCATORS["COLUMN_HEADER_BLOCK"])
                header_text = header_block.text.replace("\n", " ").strip() 
                all_headers.append(header_text)
            except NoSuchElementException:
                continue

            cell_elements = col.find_elements(*LOCATORS["COLUMN_CELL_TEXTS"])
            col_values = [cell.get_attribute("textContent").strip() for cell in cell_elements]
            # needed for debugging
            print(f"Extracted Column '{header_text}': Found {len(cell_elements)} rows.")
            
            all_columns_data.append(col_values)
            
        rows = list(zip(*all_columns_data))
        write_csv("table.csv", all_headers, rows)
        
    except TimeoutException:
        print("[ERROR] Table not found or failed to load.")
    except Exception as e:
        print(f"[ERROR] An unexpected error occurred extracting table: {e}")

# Docgnut chart data extraction
def extract_chart_data(driver):
    """
    Iterates through chart slices. 
    Expects structure: <g class="slice"> -> <text> -> <tspan>Label</tspan> <tspan>Value</tspan>
    """
    try:
        slices = driver.find_elements(*LOCATORS["CHART_SLICES"])
        extracted_data = []

        for slice_element in slices:
            try:
                tspans = slice_element.find_elements(By.TAG_NAME, "tspan")
                if len(tspans) >= 2:  # We need at least 2 tspans to have valid data.
                    facility_type = tspans[0].text.strip()
                    time_value = tspans[1].text.strip()
                    
                    if facility_type and time_value:
                        extracted_data.append([facility_type, time_value])

            except Exception as inner_e:
                continue

        if not extracted_data:
            return [["No Data Visible"]]

        return extracted_data

    except Exception as e:
        return [[f"Error extracting data: {str(e)}"]]

# Dougnut chart interaction logic to take screenshots and extract data
def process_doughnut_chart(driver):
    wait = WebDriverWait(driver, 10)

    try:
       
        chart_area = wait.until(EC.visibility_of_element_located(LOCATORS["CHART_CONTAINER"]))
        legend_items = driver.find_elements(*LOCATORS["LEGEND_ITEMS"])
        # Without chart fully in viewport schreenshot wasa failing and half cut off
        driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'nearest'});", chart_area)
        time.sleep(1)

        chart_area.screenshot("screenshot0.png")
        initial_data = extract_chart_data(driver)
        write_csv("doughnut0.csv", ["Chart Data"], initial_data)

        for i, item in enumerate(legend_items, start=1):
            try:
                item_name = item.text
                print(f"Applying Filter {i}: Clicking '{item_name}'")

                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", item)
                item.click()
        
                time.sleep(1.5)
                
                screenshot_name = f"screenshot{i}.png"
    
                driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'nearest'});", chart_area)
                
                chart_area.screenshot(screenshot_name)
                print(f"Captured {screenshot_name}")
                
                current_data = extract_chart_data(driver)
                csv_name = f"doughnut{i}.csv"
                write_csv(csv_name, ["Chart Data"], current_data)
                
                if i+1 == len(legend_items):
                    print("Edge Case Check: All filters toggled.")

            except StaleElementReferenceException:
                print(f"[WARN] Element went stale on iteration {i}.")
            except Exception as e:
                print(f"[ERROR] Failed interaction on filter {i}: {e}")

    except TimeoutException:
        print("[ERROR] Chart elements not found.")



if __name__ == "__main__":
    
    with SeleniumDriverContext() as driver:
        print(f"Opening Report: {URL}")
        try:
            driver.get(URL)

            time.sleep(2) 
            process_table(driver)
            process_doughnut_chart(driver)
            
            print("\nDone")
            
        except Exception as e:
            print(f"[FATAL ERROR] Main execution failed: {e}")