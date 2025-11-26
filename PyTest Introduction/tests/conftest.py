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

@pytest.fixture(scope="session")
def path_to_file():
    """
    Returns the path to the CSV file. 
    This acts as the source for the csv_data fixture.
    P.S: In a real-world scenario, this could be made configurable. Meaning that the path
    could be passed via command line or environment variable. Just for simplicity, it's hardcoded here. 
    But still changes accordingly what was asked. Hope its correct now :)
    """
    return "../src/data/data.csv"

# Fixture to read the CSV file
@pytest.fixture(scope="session")
def csv_data(path_to_file):
    """
    Reads the data from the CSV file and returns it as a pandas DataFrame.
    The fixture has a 'session' scope, so the file is only read once per test session.
    """
    # Path is relative to the tests directory where pytest is run
#   file_path = "../src/data/data.csv"
    try:
        df = pd.read_csv(path_to_file)
        return df
    except FileNotFoundError:
        pytest.fail(f"The data file was not found at path: {path_to_file}", pytrace=False)

@pytest.fixture(scope="session")
def schema_validator():
    """
    Compares the schema of a DataFrame against an expected schema.
    """
    def _validate(actual_schema, expected_schema):
        assert actual_schema == expected_schema, \
            f"Schema mismatch. Expected {expected_schema}, but got {actual_schema}"
    
    return _validate