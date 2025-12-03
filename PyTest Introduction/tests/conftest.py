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
def read_csv_file():
    """
    Factory fixture.
    Returns a FUNCTION that accepts a file path and returns a DataFrame.
    """
    def _read_csv(path_to_file):
        try:
            df = pd.read_csv(path_to_file)
            return df
        except FileNotFoundError:
            pytest.fail(f"The data file was not found at path: {path_to_file}", pytrace=False)
    
    return _read_csv

@pytest.fixture(scope="session")
def schema_validator():
    """
    Compares the schema of a DataFrame against an expected schema.
    """
    def _validate(actual_schema, expected_schema):
        assert actual_schema == expected_schema, \
            f"Schema mismatch. Expected {expected_schema}, but got {actual_schema}"
    
    return _validate