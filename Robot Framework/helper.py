import pandas as pd
import os
from robot.libraries.BuiltIn import BuiltIn
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException

class helper:
    
    ROBOT_LIBRARY_SCOPE = 'TEST SUITE'

    def get_html_table_data(self, locator_strategy="css selector", locator_value="g.table"):
        """
        Extracts data from the SVG table in the browser.
        Returns a Pandas DataFrame with raw string data.
        """
        
        selenium_lib = BuiltIn().get_library_instance('SeleniumLibrary')
        driver = selenium_lib.driver

        container = driver.find_element(getattr(By, locator_strategy.upper().replace(" ", "_")), locator_value)
        columns = container.find_elements(By.CLASS_NAME, "y-column")
        
        all_headers = []
        all_columns_data = []

        for col in columns:
            try:
                header_block = col.find_element(By.ID, "header")
                header_text = header_block.text.replace("\n", " ").strip()
                all_headers.append(header_text)
            except NoSuchElementException:
                print("[WARNING] Column without header found, skipping...")
                continue

            cell_elements = col.find_elements(By.CSS_SELECTOR, ".column-block[id*='cells'] .cell-text")
            col_values = [cell.get_attribute("textContent").strip() for cell in cell_elements]
            all_columns_data.append(col_values)

        rows = list(zip(*all_columns_data))
        df = pd.DataFrame(rows, columns=all_headers)

        print(f"[DONE] HTML Data Loaded: {len(df)} rows.")
        return df

    def read_parquet_data(self, folder_path, filter_date=None):
        """
        Reads a parquet dataset, filters it.
        """
        try:
            df = pd.read_parquet(folder_path)
   
            df.columns = [c.replace('_', ' ').title() for c in df.columns]
            for col in df.columns:
                if "Date" in col:
                    df[col] = df[col].astype(str)

            if filter_date:
                df = df[df['Visit Date'] == filter_date]
                print(f"[DONE] Filtered Parquet data by date: {filter_date}")

            print(f"[DONE] Parquet Data Loaded: {len(df)} rows.")
            return df

        except Exception as e:
            raise Exception(f"[ERROR] Failed to read Parquet: {e}")

    def _normalize_types(self, df):
        """
        Internal helper: Tries to convert columns to numeric. 
        If it fails (e.g. text/dates), ensures they are strings.
        This ensures '24' (str) and 24.0 (float) both become comparable numbers.
        """
        for col in df.columns:
            try:
                df[col] = pd.to_numeric(df[col], errors='raise')
            except (ValueError, TypeError):
                df[col] = df[col].astype(str)
        return df

    def compare_dataframes(self, df_html, df_parquet):
        """
        Compares
        """
       
        df_html = self._normalize_types(df_html)
        df_parquet = self._normalize_types(df_parquet)

        sort_cols = list(df_html.columns)
        df_html_sorted = df_html.sort_values(by=sort_cols).reset_index(drop=True)
        df_parquet_sorted = df_parquet.sort_values(by=sort_cols).reset_index(drop=True)

        if df_html_sorted.equals(df_parquet_sorted):
            print("[SUCCESS] DataFrames match exactly.")
            return True
        else:
            print("[ERROR] Data mismatch found.")
            print(f"[DONE] HTML Rows: {len(df_html_sorted)}")
            print(f"[DONE] Parquet Rows: {len(df_parquet_sorted)}")
            
            diff = df_html_sorted.compare(df_parquet_sorted)
            raise AssertionError(f"[ERROR] DataFrames do not match!\nDifferences:\n{diff}")
        
"""
Comment from my side:
So, I am attaching 3 datasets here: 
1. data_valid.parquet  is the same data as in HRML Table, therefore running code against that dataset passes with no isses.
2. data_not_valid.parquet has some differences compared to HTML Table, therefore running code against that dataset fails with proper diff message.
3. data_not_valid_diff_header.parquet has the same data as HTML Table but with different column headers, which should also cause a failure.

When all three of them are in dataset folder, the function tries to read and put them in one big dataset, which fails, due to header mismatches. Therefore, For test to pass successfully, I keep only data_valid.parquet in the dataset folder.
I don't know if this as you had in mind for the task. If not I will modify parquet reading function.
Thanks in advance! :) 🐟
"""