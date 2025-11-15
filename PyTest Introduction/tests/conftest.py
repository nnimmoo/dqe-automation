import pytest
import pandas as pd

# Pytest hook to mark unmarked tests with a custom mark
def pytest_collection_modifyitems(config, items):
    """
    This hook is called after test collection. It iterates through all collected
    tests and adds the 'unmarked' mark to any test that does not have any
    other marks.
    """
    for item in items:
        if not any(item.iter_markers()):
            item.add_marker(pytest.mark.unmarked)

# Fixture to read the CSV file
@pytest.fixture(scope="session")
def csv_data():
    """
    Reads the data from the CSV file and returns it as a pandas DataFrame.
    The fixture has a 'session' scope, so the file is only read once per test session.
    """
    # Path is relative to the tests directory where pytest is run
    file_path = "../src/data/data.csv"
    try:
        df = pd.read_csv(file_path)
        return df
    except FileNotFoundError:
        pytest.fail(f"The data file was not found at path: {file_path}", pytrace=False)

