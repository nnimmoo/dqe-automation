import time
import os
import pandas as pd

from selenium import webdriver
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException


class SeleniumWebDriverContextManager:
    def __init__(self):
        pass
    def __enter__(self):
        pass
    def __exit__(self, exc_type, exc_value, traceback):
        pass

# if __name__ == "__main__":
    # with SeleniumWebDriverContextManager() as driver:
        # file_path = ...
        # drivet.get(...)
        # ...
    