import pytest
import pandas as pd
from datetime import datetime, date
import logging

@pytest.mark.postgres_data
class TestPatientsDataQuality:
    """
    Test suite for validating Patients table data quality.
    Tests both PostgreSQL source data and Parquet transformations.
    """
    
    @pytest.fixture(scope="class")
    def patients_postgres_data(self, postgres_connector):
        """Get patients data from PostgreSQL."""
        query = """
        SELECT 
            id,
            external_id,
            first_name,
            last_name,
            address,
            date_of_birth
        FROM patients
        ORDER BY id
        """
        with postgres_connector as pg_conn:
            return pg_conn.get_data_sql(query)
    
  
    @pytest.fixture(scope="class")
    def patients_with_full_name(self, postgres_connector):
        """Get patients data with full_name transformation."""
        query = """
        SELECT 
            id,
            external_id,
            first_name,
            last_name,
            CONCAT(first_name, ' ', last_name) as full_name,
            address,
            date_of_birth
        FROM patients
        WHERE first_name IS NOT NULL AND last_name IS NOT NULL
        ORDER BY id
        """
        with postgres_connector as pg_conn:
            return pg_conn.get_data_sql(query)
    
    def test_patients_table_exists_and_not_empty(self, patients_postgres_data, data_quality_library):
        """Test that patients table exists and contains data."""
        data_quality_library.check_dataset_is_not_empty(
            patients_postgres_data, 
            min_rows=1
        )
        
        logging.info(f"Patients table contains {len(patients_postgres_data)} records")
    
    def test_patients_required_columns_exist(self, patients_postgres_data, data_quality_library):
        """Test that all required columns exist in patients table."""
        required_columns = [
            'id', 'external_id', 'first_name', 'last_name', 
            'address', 'date_of_birth'
        ]
        
        data_quality_library.check_column_exists(
            patients_postgres_data, 
            required_columns
        )
    
    def test_patients_data_types(self, patients_postgres_data, data_quality_library):
        """Test that patients columns have correct data types."""
        expected_types = {
            'id': 'int',
            'external_id': 'int',
            'first_name': 'object',
            'last_name': 'object',
            'address': 'object',
            'date_of_birth': 'object'
        }
        
        data_quality_library.check_data_types(
            patients_postgres_data, 
            expected_types
        )
    
    def test_patients_primary_key_uniqueness(self, patients_postgres_data, data_quality_library):
        """Test that patient ID is unique (primary key constraint)."""
        data_quality_library.check_uniqueness(
            patients_postgres_data,
            column_names=['id'],
            allow_nulls=False
        )
    
    def test_patients_external_id_uniqueness(self, patients_postgres_data, data_quality_library):
        """Test that external_id is unique."""
        data_quality_library.check_uniqueness(
            patients_postgres_data,
            column_names=['external_id'],
            allow_nulls=False
        )
    
    def test_patients_no_null_values_critical_fields(self, patients_postgres_data, data_quality_library):
        """Test that critical fields don't contain null values."""
        critical_fields = ['id', 'external_id', 'first_name', 'last_name', 'date_of_birth']
        
        data_quality_library.check_not_null_values(
            patients_postgres_data,
            column_names=critical_fields,
            max_null_percentage=0.0
        )
    
    def test_patients_name_fields_not_empty(self, patients_postgres_data):
        """Test that first_name and last_name are not empty strings."""
        # Test first_name
        first_names = patients_postgres_data['first_name'].dropna()
        empty_first_names = first_names[first_names.str.strip() == '']
        assert len(empty_first_names) == 0, f"Found {len(empty_first_names)} empty first names"
        
        # Test last_name
        last_names = patients_postgres_data['last_name'].dropna()
        empty_last_names = last_names[last_names.str.strip() == '']
        assert len(empty_last_names) == 0, f"Found {len(empty_last_names)} empty last names"
        
        # Check minimum length
        min_first_name_length = first_names.str.len().min()
        min_last_name_length = last_names.str.len().min()
        
        assert min_first_name_length >= 1, f"First name too short: minimum length is {min_first_name_length}"
        assert min_last_name_length >= 1, f"Last name too short: minimum length is {min_last_name_length}"
    
    def test_patients_date_of_birth_validity(self, patients_postgres_data):
        """Test that date_of_birth values are valid and reasonable."""
        dob_series = patients_postgres_data['date_of_birth'].dropna()
        
        # Convert to datetime if not already
        if not pd.api.types.is_datetime64_any_dtype(dob_series):
            dob_series = pd.to_datetime(dob_series)
        
        current_date = datetime.now().date()
        
        # Check for future dates
        future_dates = dob_series[dob_series.dt.date > current_date]
        assert len(future_dates) == 0, f"Found {len(future_dates)} future birth dates"
        
        # Check for unreasonably old dates (older than 150 years)
        min_reasonable_date = datetime(current_date.year - 150, 1, 1).date()
        too_old_dates = dob_series[dob_series.dt.date < min_reasonable_date]
        assert len(too_old_dates) == 0, f"Found {len(too_old_dates)} unreasonably old birth dates"
        
    
    def test_patients_full_name_transformation(self, patients_with_full_name):
        """Test that full_name transformation is correct."""
        for _, row in patients_with_full_name.iterrows():
            expected_full_name = f"{row['first_name']} {row['last_name']}"
            actual_full_name = row['full_name']
            
            assert actual_full_name == expected_full_name, (
                f"Full name mismatch for patient {row['id']}: "
                f"expected '{expected_full_name}', got '{actual_full_name}'"
            )
    
    def test_patients_full_name_not_null_after_transformation(self, patients_with_full_name, data_quality_library):
        """Test that full_name field is not null after transformation."""
        data_quality_library.check_not_null_values(
            patients_with_full_name,
            column_names=['full_name'],
            max_null_percentage=0.0
        )
    
    def test_patients_no_duplicates(self, patients_postgres_data, data_quality_library):
        """Test that there are no duplicate patient records."""
        data_quality_library.check_duplicates(
            patients_postgres_data,
            column_names=['first_name', 'last_name', 'date_of_birth'],
            max_duplicates=0
        )
