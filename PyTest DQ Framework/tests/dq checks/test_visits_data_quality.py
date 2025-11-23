import pytest
import pandas as pd
from datetime import datetime, timedelta
import logging

@pytest.mark.postgres_data
class TestVisitsDataQuality:
    """
    Test suite for validating Visits table data quality.
    Tests both PostgreSQL source data and Parquet transformations.
    """
    
    @pytest.fixture(scope="class")
    def visits_postgres_data(self, postgres_connector):
        """Get visits data from PostgreSQL."""
        query = """
        SELECT 
            id,
            patient_id,
            facility_id,
            visit_timestamp,
            treatment_cost,
            duration_minutes
        FROM visits
        ORDER BY id
        """
        with postgres_connector as pg_conn:
            return pg_conn.get_data_sql(query)
    
    
    @pytest.fixture(scope="class")
    def visits_with_transformations(self, postgres_connector):
        """Get visits data with required transformations."""
        query = """
        SELECT 
            id,
            patient_id,
            facility_id,
            visit_timestamp,
            visit_timestamp::date as visit_date,
            treatment_cost,
            duration_minutes,
            ROUND(AVG(duration_minutes) OVER (PARTITION BY facility_id, visit_timestamp::date), 2) as avg_time_spent,
            SUM(treatment_cost) OVER (PARTITION BY facility_id, visit_timestamp::date) as sum_treatment_cost
        FROM visits
        WHERE visit_timestamp IS NOT NULL 
          AND duration_minutes IS NOT NULL 
          AND treatment_cost IS NOT NULL
        ORDER BY id
        """
        with postgres_connector as pg_conn:
            return pg_conn.get_data_sql(query)
    
    def test_visits_table_exists_and_not_empty(self, visits_postgres_data, data_quality_library):
        """Test that visits table exists and contains data."""
        data_quality_library.check_dataset_is_not_empty(
            visits_postgres_data, 
            min_rows=1
        )
        
        logging.info(f"Visits table contains {len(visits_postgres_data)} records")
    
    def test_visits_required_columns_exist(self, visits_postgres_data, data_quality_library):
        """Test that all required columns exist in visits table."""

        required_columns = [
            'id', 'patient_id', 'facility_id', 'visit_timestamp', 
            'treatment_cost', 'duration_minutes'
        ]
        
        data_quality_library.check_column_exists(
            visits_postgres_data, 
            required_columns
        )
    
    def test_visits_data_types(self, visits_postgres_data, data_quality_library):
        """Test that visits columns have correct data types."""
        expected_types = {
            'id': 'int',
            'patient_id': 'int',
            'facility_id': 'int',
            'visit_timestamp': 'datetime',
            'treatment_cost': 'float',
            'duration_minutes': 'int'
        }
        
        data_quality_library.check_data_types(
            visits_postgres_data, 
            expected_types
        )
    
    def test_visits_primary_key_uniqueness(self, visits_postgres_data, data_quality_library):
        """Test that visit ID is unique (primary key constraint)."""
        data_quality_library.check_uniqueness(
            visits_postgres_data,
            column_names=['id'],
            allow_nulls=False
        )
    
    def test_visits_no_null_values_critical_fields(self, visits_postgres_data, data_quality_library):
        """Test that critical fields don't contain null values."""
        critical_fields = ['id', 'patient_id', 'facility_id', 'visit_timestamp']
        
        data_quality_library.check_not_null_values(
            visits_postgres_data,
            column_names=critical_fields,
            max_null_percentage=0.0
        )
    
    def test_visits_foreign_key_constraints(self, visits_postgres_data, postgres_connector):
        """Test that foreign key relationships are valid."""
        with postgres_connector as pg_conn:
            # Check patient_id references
            patient_check_query = """
            SELECT COUNT(*) as invalid_patients
            FROM visits v
            LEFT JOIN patients p ON v.patient_id = p.id
            WHERE p.id IS NULL AND v.patient_id IS NOT NULL
            """
            invalid_patients = pg_conn.get_data_sql(patient_check_query)
            assert invalid_patients.iloc[0]['invalid_patients'] == 0, "Found visits with invalid patient_id references"
            
            # Check facility_id references
            facility_check_query = """
            SELECT COUNT(*) as invalid_facilities
            FROM visits v
            LEFT JOIN facilities f ON v.facility_id = f.id
            WHERE f.id IS NULL AND v.facility_id IS NOT NULL
            """
            invalid_facilities = pg_conn.get_data_sql(facility_check_query)
            assert invalid_facilities.iloc[0]['invalid_facilities'] == 0, "Found visits with invalid facility_id references"
    
    def test_visits_timestamp_validity(self, visits_postgres_data):
        """Test that visit_timestamp values are valid and reasonable."""
        timestamps = visits_postgres_data['visit_timestamp'].dropna()
        
        # Convert to datetime if not already
        if not pd.api.types.is_datetime64_any_dtype(timestamps):
            timestamps = pd.to_datetime(timestamps)
        
        current_time = datetime.now()
        
        # Check for future timestamps
        future_visits = timestamps[timestamps > current_time]
        assert len(future_visits) == 0, f"Found {len(future_visits)} future visit timestamps"
        
        # Check for unreasonably old timestamps (older than 50 years)
        min_reasonable_date = current_time - timedelta(days=50*365)
        too_old_visits = timestamps[timestamps < min_reasonable_date]
        assert len(too_old_visits) == 0, f"Found {len(too_old_visits)} unreasonably old visit timestamps"
    
    def test_visits_treatment_cost_validity(self, visits_postgres_data, data_quality_library):
        """Test that treatment_cost values are valid."""
        # Check for non-negative values
        data_quality_library.check_value_range(
            visits_postgres_data,
            column_name='treatment_cost',
            min_value=0.0,
            max_value=1000000.0  # Reasonable upper limit
        )
        
        # Check for null values in treatment_cost
        data_quality_library.check_not_null_values(
            visits_postgres_data,
            column_names=['treatment_cost'],
            max_null_percentage=5.0  # Allow up to 5% null values
        )
    
    def test_visits_duration_minutes_validity(self, visits_postgres_data, data_quality_library):
        """Test that duration_minutes values are valid."""
        # Check for reasonable range (1 minute to 24 hours)
        data_quality_library.check_value_range(
            visits_postgres_data,
            column_name='duration_minutes',
            min_value=1,
            max_value=1440  # 24 hours in minutes
        )
        
        # Check for null values in duration_minutes
        data_quality_library.check_not_null_values(
            visits_postgres_data,
            column_names=['duration_minutes'],
            max_null_percentage=5.0  # Allow up to 5% null values
        )
    
    def test_visits_date_transformation(self, visits_with_transformations):
        """Test that visit_date transformation is correct."""
        for _, row in visits_with_transformations.iterrows():
            visit_timestamp = pd.to_datetime(row['visit_timestamp'])
            expected_visit_date = visit_timestamp.date()
            actual_visit_date = pd.to_datetime(row['visit_date']).date()
            
            assert actual_visit_date == expected_visit_date, (
                f"Visit date mismatch for visit {row['id']}: "
                f"expected {expected_visit_date}, got {actual_visit_date}"
            )
    
    def test_visits_avg_time_spent_calculation(self, visits_with_transformations):
        """Test that avg_time_spent calculation is correct and rounded to 2 decimal places."""
        # Group by facility and visit_date to verify averages
        grouped = visits_with_transformations.groupby(['facility_id', 'visit_date'])
        
        for (facility_id, visit_date), group in grouped:
            expected_avg = round(group['duration_minutes'].mean(), 2)
            actual_avg = group['avg_time_spent'].iloc[0]  # Should be same for all rows in group
            
            assert abs(actual_avg - expected_avg) < 0.01, (
                f"Average time spent mismatch for facility {facility_id} on {visit_date}: "
                f"expected {expected_avg}, got {actual_avg}"
            )
            
            # Check that it's rounded to 2 decimal places
            decimal_places = len(str(actual_avg).split('.')[-1]) if '.' in str(actual_avg) else 0
            assert decimal_places <= 2, f"avg_time_spent not properly rounded: {actual_avg}"
    
    def test_visits_sum_treatment_cost_calculation(self, visits_with_transformations):
        """Test that sum_treatment_cost calculation is correct and non-negative."""
        # Group by facility and visit_date to verify sums
        grouped = visits_with_transformations.groupby(['facility_id', 'visit_date'])
        
        for (facility_id, visit_date), group in grouped:
            expected_sum = group['treatment_cost'].sum()
            actual_sum = group['sum_treatment_cost'].iloc[0]  # Should be same for all rows in group
            
            assert abs(actual_sum - expected_sum) < 0.01, (
                f"Sum treatment cost mismatch for facility {facility_id} on {visit_date}: "
                f"expected {expected_sum}, got {actual_sum}"
            )
            
            # Check that sum is non-negative
            assert actual_sum >= 0, f"Sum treatment cost is negative: {actual_sum}"
    
    def test_visits_transformation_not_null_requirements(self, visits_with_transformations, data_quality_library):
        """Test that transformed fields are not null."""
        transformation_fields = ['visit_date', 'avg_time_spent', 'sum_treatment_cost']
        
        data_quality_library.check_not_null_values(
            visits_with_transformations,
            column_names=transformation_fields,
            max_null_percentage=0.0
        )
    
    def test_visits_no_duplicates(self, visits_postgres_data, data_quality_library):
        """Test that there are no duplicate visit records."""
        data_quality_library.check_duplicates(
            visits_postgres_data,
            column_names=['patient_id', 'facility_id', 'visit_timestamp'],
            max_duplicates=0
        )
  