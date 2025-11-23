import pytest
import pandas as pd
from typing import Dict, Any
import logging

@pytest.mark.postgres_data
class TestFacilitiesDataQuality:
    """
    Test suite for validating Facilities table data quality.
    Tests both PostgreSQL source data and Parquet transformations.
    """
    
    @pytest.fixture(scope="class")
    def facilities_postgres_data(self, postgres_connector):
        """Get facilities data from PostgreSQL."""
        query = """
        SELECT 
            id,
            external_id,
            facility_name,
            facility_type,
            address,
            city,
            state
        FROM facilities
        ORDER BY id
        """
        with postgres_connector as pg_conn:
            return pg_conn.get_data_sql(query)
    

    def test_facilities_table_exists_and_not_empty(self, facilities_postgres_data, data_quality_library):
        """Test that facilities table exists and contains data."""
        data_quality_library.check_dataset_is_not_empty(
            facilities_postgres_data, 
            min_rows=1
        )
        
        logging.info(f"Facilities table contains {len(facilities_postgres_data)} records")
    
    def test_facilities_required_columns_exist(self, facilities_postgres_data, data_quality_library):
        """Test that all required columns exist in facilities table."""
        required_columns = [
            'id', 'external_id', 'facility_name', 'facility_type', 
            'address', 'city', 'state'
        ]
        
        data_quality_library.check_column_exists(
            facilities_postgres_data, 
            required_columns
        )
    
    def test_facilities_data_types(self, facilities_postgres_data, data_quality_library):
        """Test that facilities columns have correct data types."""
        expected_types = {
            'id': 'int',
            'external_id': 'int', 
            'facility_name': 'object',
            'facility_type': 'object',
            'address': 'object',
            'city': 'object',
            'state': 'object'
        }
        
        data_quality_library.check_data_types(
            facilities_postgres_data, 
            expected_types
        )
    
    def test_facilities_primary_key_uniqueness(self, facilities_postgres_data, data_quality_library):
        """Test that facility ID is unique (primary key constraint)."""
        data_quality_library.check_uniqueness(
            facilities_postgres_data,
            column_names=['id'],
            allow_nulls=False
        )
    
    def test_facilities_external_id_uniqueness(self, facilities_postgres_data, data_quality_library):
        """Test that external_id is unique."""
        data_quality_library.check_uniqueness(
            facilities_postgres_data,
            column_names=['external_id'],
            allow_nulls=False
        )
    
    def test_facilities_no_null_values_critical_fields(self, facilities_postgres_data, data_quality_library):
        """Test that critical fields don't contain null values."""
        critical_fields = ['id', 'external_id', 'facility_name', 'facility_type']
        
        data_quality_library.check_not_null_values(
            facilities_postgres_data,
            column_names=critical_fields,
            max_null_percentage=0.0
        )
    
    def test_facilities_facility_name_not_empty(self, facilities_postgres_data):
        """Test that facility_name is not empty string."""
        facility_names = facilities_postgres_data['facility_name'].dropna()
        empty_names = facility_names[facility_names.str.strip() == '']
        
        assert len(empty_names) == 0, f"Found {len(empty_names)} empty facility names"
        
        # Check minimum length
        min_length = facility_names.str.len().min()
        assert min_length >= 2, f"Facility name too short: minimum length is {min_length}"
    

    
    def test_facilities_states_validity(self, facilities_postgres_data):
        valid_states = ["Alabama", "Alaska", "Arizona", "Arkansas",
                        "California","Colorado","Connecticut","Delaware",
                        "Florida","Georgia","Hawaii","Idaho",
                        "Illinois","Indiana","Iowa",
                        "Kansas", "Kentucky",
                        "Louisiana",
                        "Maine","Maryland", "Massachusetts","Michigan",
                        "Minnesota", "Mississippi", "Missouri","Montana",
                        "Nebraska", "Nevada", "New Hampshire","New Jersey",
                        "New Mexico","New York", "North Carolina","North Dakota",
                        "Ohio","Oklahoma", "Oregon", "Pennsylvania",
                        "Rhode Island","South Carolina","South Dakota","Tennessee",
                        "Texas", "Utah", "Vermont","Virginia",
                        "Washington","West Virginia","Wisconsin","Wyoming" ]

        state_column = facilities_postgres_data['state'].dropna()
        
        # Check that all are valid states
        invalid_states = state_column[~state_column.isin(valid_states)]
        assert len(invalid_states) == 0, f"Invalid state formats found: {invalid_states.tolist()}"
    
    def test_facilities_no_duplicates(self, facilities_postgres_data, data_quality_library):
        """Test that there are no duplicate facility records."""
        data_quality_library.check_duplicates(
            facilities_postgres_data,
            column_names=['facility_name', 'address', 'city', 'state'],
            max_duplicates=0
        )
