import pytest
import os

@pytest.fixture(scope="module")
def data(read_csv_file):
    """
    Local fixture that reads the specific file for these tests.
    It calls the 'read_csv_file' factory from conftest.py.
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))
    csv_file_path = os.path.join(current_dir, "..", "..", "src", "data", "data.csv")
    return read_csv_file(csv_file_path)


# Test: Validate that file is not empty
# Mark: - (will be marked 'unmarked' by the hook)
def test_file_not_empty(data):
    """Validates that the CSV file is not empty."""
    assert not data.empty, "CSV file is empty."

# Test: Validate the schema of the file (id, name, age, email)
# Mark: validate_csv
@pytest.mark.validate_csv
def test_validate_schema(data, schema_validator):
    """Validates that the CSV has the expected columns."""
    expected_schema = ['id', 'name', 'age', 'email', 'is_active']
    actual_schema = data.columns.tolist()
    schema_validator(actual_schema, expected_schema)

# Test: Validate that the age column contains valid values (0-100
# Mark: validate_csv, skip
@pytest.mark.validate_csv
@pytest.mark.skip(reason="Age validation is currently disabled.")
def test_age_column_valid(data):
    """Validates that all ages are between 0 and 100."""
    ages = data['age']
    assert all(0 <= age <= 100 for age in ages), "Age column contains values out of the 0-100 range."

# Test: Validate that the email contains valid email format
# Mark: validate_csv
@pytest.mark.validate_csv
def test_email_column_valid(data):
    """Validates the format of email addresses in the email column."""
    email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    invalid_emails = [
        email for email in data['email'] if not re.match(email_regex, email)
    ]
    assert not invalid_emails, f"Invalid email addresses found: {invalid_emails}"

# Test: Validate there are no duplicate rows
# Mark: validate_csv, xfail
@pytest.mark.validate_csv
@pytest.mark.xfail(reason="Expected to find duplicate rows in the data.")
def test_no_duplicate_rows(data):
    """Validates that there are no duplicate rows in the CSV file."""
    duplicates = data[data.duplicated()]
    assert duplicates.empty, f"Found duplicate rows: \n{duplicates}"
    
# Test: Validate that: is_active = False for id = 1, is_active = True for id = 2
# Mark: parametrize("id", "is_active", [ ... ])
@pytest.mark.parametrize("player_id, expected_status", [
    (1, False),
    (2, True)
])
def test_is_active_status_parametrized(data, player_id, expected_status):
    """Validates the 'is_active' status for specific player IDs."""
    player_row = data[data['id'] == player_id]
    assert not player_row.empty, f"Player with id {player_id} not found."
    
    actual_status = player_row['is_active'].iloc[0]
    assert actual_status == expected_status, \
        f"For id {player_id}, expected is_active={expected_status}, but got {actual_status}"

# Test: Same as previous one for id = 2, but without parametrize mark.
# Mark: - (will be marked 'unmarked' by the hook)
def test_is_active_for_player_2(data):
    """Validates the 'is_active' status for player with id=2."""
    player_id = 2
    expected_status = True
    
    player_row = data[data['id'] == player_id]
    assert not player_row.empty, f"Player with id {player_id} not found."
    
    actual_status = player_row['is_active'].iloc[0]
    assert actual_status == expected_status, \
        f"For id {player_id}, expected is_active={expected_status}, but got {actual_status}"