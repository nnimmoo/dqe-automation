"""
Description: Data Quality checks for facility_name_min_time_spent_per_visit_date Parquet files.
Data Source: Parquet files located in /parquet_data/facility_name_min_time_spent_per_visit_date/
Data Target: PostgreSQL source table 'visits' and 'facilities' for comparison.
Requirement(s): TICKET-1
Author(s): Nino Goguadze
"""

import pytest
import pandas as pd
from pathlib import Path
from datetime import datetime, date
import logging
import os
import re
from typing import List, Dict, Any

@pytest.mark.parquet_data
@pytest.mark.data_transformation
class TestFacilityNameMinTimeSpentPerVisitDate:
    """
    Test suite for validating facility_name_min_time_spent_per_visit_date Parquet files.
    Tests partitioned data structure, partition consistency, and data quality.
    """
    
@pytest.fixture(scope="class")
def parquet_base_directory(self, request):
    """Get the base directory for facility_name_min_time_spent_per_visit_date partitions."""
    
    base_path_str = request.config.getoption("--facility-name-min-time-path")
    
    if not base_path_str:
        base_path_str = os.getenv("FACILITY_NAME_MIN_TIME_PATH")
    
    if not base_path_str:
        root_path = request.config.getoption("--parquet-root-path") or os.getenv("PARQUET_ROOT_PATH", "/parquet_data")
        base_path_str = os.path.join(root_path, "facility_name_min_time_spent_per_visit_date")
    
    base_path = Path(base_path_str)
    
    if not base_path.exists():
        pytest.skip(f"Parquet data directory not found: {base_path}")
    
    logging.info(f"Using facility_name_min_time_spent_per_visit_date path: {base_path}")
    return base_path
    
    @pytest.fixture(scope="class")
    def partition_directories(self, parquet_base_directory):
        """Get all partition directories (year-month folders)."""
        partition_dirs = []
        
        for item in parquet_base_directory.iterdir():
            if item.is_dir() and re.match(r'partition_date=\d{4}-\d{2}', item.name):
                partition_dirs.append(item)
        
        partition_dirs.sort() 
        
        if not partition_dirs:
            pytest.skip("No partition directories found")
        
        return partition_dirs
    
    @pytest.fixture(scope="class")
    def all_parquet_data(self, partition_directories, parquet_reader):
        """Load all data from all partitions."""
        all_data = []
        
        for partition_dir in partition_directories:
            # Find parquet files in the partition directory
            parquet_files = list(partition_dir.glob("*.parquet"))
            
            for parquet_file in parquet_files:
                try:
                    df = pd.read_parquet(parquet_file)
                    # Add partition information
                    partition_date = partition_dir.name.replace('partition_date=', '')
                    df['_partition_date'] = partition_date
                    df['_partition_path'] = str(partition_dir)
                    df['_file_path'] = str(parquet_file)
                    all_data.append(df)
                except Exception as e:
                    logging.error(f"Failed to read {parquet_file}: {e}")
        
        if not all_data:
            pytest.skip("No parquet data could be loaded")
        
        combined_df = pd.concat(all_data, ignore_index=True)
        logging.info(f"Loaded {len(combined_df)} total records from {len(all_data)} partition files")
        
        return combined_df
    
    @pytest.fixture(scope="class")
    def source_data_for_comparison(self, postgres_connector):
        """Get source data from PostgreSQL for comparison."""
        query = """
        SELECT 
            f.facility_name,
            DATE_TRUNC('month', v.visit_timestamp)::date as visit_month,
            v.visit_timestamp::date as visit_date,
            MIN(v.duration_minutes) as min_time_spent
        FROM visits v
        JOIN facilities f ON v.facility_id = f.id
        WHERE v.duration_minutes IS NOT NULL 
          AND v.visit_timestamp IS NOT NULL
          AND f.facility_name IS NOT NULL
        GROUP BY f.facility_name, DATE_TRUNC('month', v.visit_timestamp)::date, v.visit_timestamp::date
        ORDER BY visit_month, visit_date, f.facility_name
        """
        
        try:
            with postgres_connector as pg_conn:
                return pg_conn.get_data_sql(query)
        except Exception as e:
            logging.warning(f"Could not load source data for comparison: {e}")
            return pd.DataFrame()
    
    def test_partition_directories_exist(self, parquet_base_directory, partition_directories):
        """Test that partition directories exist and follow correct naming convention."""
        assert len(partition_directories) > 0, "No partition directories found"
        
        # Test naming convention
        for partition_dir in partition_directories:
            assert re.match(r'partition_date=\d{4}-\d{2}$', partition_dir.name), (
                f"Invalid partition directory name: {partition_dir.name}. "
                f"Expected format: partition_date=YYYY-MM"
            )
        
        logging.info(f"Found {len(partition_directories)} valid partition directories")
     
    def test_partition_date_range_consistency(self, partition_directories):
        """Test that partition dates are consistent and cover expected range."""
        partition_dates = []
        
        for partition_dir in partition_directories:
            date_str = partition_dir.name.replace('partition_date=', '')
            try:
                partition_date = datetime.strptime(date_str, '%Y-%m').date()
                partition_dates.append(partition_date)
            except ValueError:
                pytest.fail(f"Invalid date format in partition: {date_str}")
        
        partition_dates.sort()
        
        min_partition_date = min(partition_dates)
        max_partition_date = max(partition_dates)
        
        # Check that dates are reasonable (not in future, not too old)
        current_date = date.today()
        assert min_partition_date <= current_date, f"Future partition date found: {min_partition_date}"  
        assert max_partition_date <= current_date, f"Future partition date found: {max_partition_date}"  

        logging.info(f"Partition date range: {min_partition_date} to {max_partition_date}")
        
        return min_partition_date, max_partition_date
    
    def test_each_partition_contains_parquet_files(self, partition_directories):
        """Test that each partition directory contains at least one parquet file."""
        empty_partitions = []
        total_files = 0
        
        for partition_dir in partition_directories:
            parquet_files = list(partition_dir.glob("*.parquet"))
            
            if not parquet_files:
                empty_partitions.append(partition_dir.name)
            else:
                total_files += len(parquet_files)
        
        assert len(empty_partitions) == 0, (
            f"Found {len(empty_partitions)} empty partitions: {empty_partitions}"
        )
        
        logging.info(f"All {len(partition_directories)} partitions contain parquet files. "
                    f"Total files: {total_files}")
    
    def test_parquet_files_readable_and_not_empty(self, partition_directories):
        """Test that all parquet files are readable and contain data."""
        unreadable_files = []
        empty_files = []
        total_records = 0
        
        for partition_dir in partition_directories:
            parquet_files = list(partition_dir.glob("*.parquet"))
            
            for parquet_file in parquet_files:
                try:
                    df = pd.read_parquet(parquet_file)
                    
                    if df.empty:
                        empty_files.append(str(parquet_file))
                    else:
                        total_records += len(df)
                        
                except Exception as e:
                    unreadable_files.append(f"{parquet_file}: {e}")
        
        assert len(unreadable_files) == 0, (
            f"Found {len(unreadable_files)} unreadable files: {unreadable_files}"
        )
        
        assert len(empty_files) == 0, (
            f"Found {len(empty_files)} empty files: {empty_files}"
        )
        
        logging.info(f"All parquet files are readable and contain data. "
                    f"Total records: {total_records}")
    
    def test_parquet_schema_consistency(self, partition_directories):
        """Test that all parquet files have consistent schema."""
        expected_columns = ['facility_name', 'visit_date', 'min_time_spent']
        schema_issues = []
        
        for partition_dir in partition_directories:
            parquet_files = list(partition_dir.glob("*.parquet"))
            
            for parquet_file in parquet_files:
                try:
                    df = pd.read_parquet(parquet_file)
                    
                    # Check columns
                    if list(df.columns) != expected_columns:
                        schema_issues.append(
                            f"{parquet_file}: Expected columns {expected_columns}, "
                            f"got {list(df.columns)}"
                        )
                    
                    # Check data types
                    if not pd.api.types.is_object_dtype(df['facility_name']):
                        schema_issues.append(f"{parquet_file}: facility_name should be object/string type")
                    
                    if not pd.api.types.is_datetime64_any_dtype(df['visit_date']) and not pd.api.types.is_object_dtype(df['visit_date']):
                        schema_issues.append(f"{parquet_file}: visit_date should be datetime or date type")
                    
                    if not pd.api.types.is_numeric_dtype(df['min_time_spent']):
                        schema_issues.append(f"{parquet_file}: min_time_spent should be numeric type")
                        
                except Exception as e:
                    schema_issues.append(f"{parquet_file}: Could not check schema - {e}")
        
        assert len(schema_issues) == 0, f"Schema consistency issues found: {schema_issues}"
        
        logging.info("All parquet files have consistent schema")
    
    def test_data_quality_within_partitions(self, all_parquet_data, data_quality_library):
        """Test data quality across all partitions."""
        # Remove internal columns added during loading
        df = all_parquet_data.drop(columns=['_partition_date', '_partition_path', '_file_path'])
        
        # Test that dataset is not empty
        data_quality_library.check_dataset_is_not_empty(df, min_rows=1)
        
        # Test required columns exist
        data_quality_library.check_column_exists(df, ['facility_name', 'visit_date', 'min_time_spent'])
        
        # Test no null values in critical fields
        data_quality_library.check_not_null_values(
            df,
            column_names=['facility_name', 'visit_date', 'min_time_spent'],
            max_null_percentage=0.0
        )
        
        # Test min_time_spent is positive and reasonable
        data_quality_library.check_value_range(
            df,
            column_name='min_time_spent',
            min_value=1,
            max_value=1440  # 24 hours in minutes
        )
        
        logging.info(f"Data quality checks passed for {len(df)} records")
    
    def test_partition_data_consistency(self, all_parquet_data):
        """Test that data in each partition matches the partition date."""
        inconsistent_partitions = []
        
        # Group by partition
        for partition_date, group in all_parquet_data.groupby('_partition_date'):
            # Convert partition_date to year-month
            try:
                partition_year_month = datetime.strptime(partition_date, '%Y-%m')
            except ValueError:
                inconsistent_partitions.append(f"Invalid partition date format: {partition_date}")
                continue
            
            # Check that all visit_dates in this partition belong to the same year-month
            visit_dates = pd.to_datetime(group['visit_date'])
            
            for visit_date in visit_dates:
                if visit_date.year != partition_year_month.year or visit_date.month != partition_year_month.month:
                    inconsistent_partitions.append(
                        f"Partition {partition_date} contains data from {visit_date.strftime('%Y-%m')}"
                    )
        
        assert len(inconsistent_partitions) == 0, (
            f"Found partitiondata inconsistencies: {inconsistent_partitions}"
        )
        
        logging.info("All partition data is consistent with partition dates")
    
    def test_facility_name_validity(self, all_parquet_data):
        """Test that facility names are valid and not empty."""
        df = all_parquet_data
        
        # Check for empty facility names
        empty_names = df[df['facility_name'].str.strip() == '']
        assert len(empty_names) == 0, f"Found {len(empty_names)} records with empty facility names"
        
        # Check minimum length
        min_length = df['facility_name'].str.len().min()
        assert min_length >= 2, f"Facility name too short: minimum length is {min_length}"
        
        # Check for reasonable facility name patterns
        facility_names = df['facility_name'].unique()
        logging.info(f"Found {len(facility_names)} unique facility names")
        
        # Log sample facility names for verification
        sample_names = facility_names[:5] if len(facility_names) >= 5 else facility_names
        logging.info(f"Sample facility names: {list(sample_names)}")
    
    def test_min_time_spent_calculation_logic(self, all_parquet_data):
        """Test that min_time_spent values are logical."""
        df = all_parquet_data
        
        # Group by facility and visit_date to check if min values make sense
        grouped = df.groupby(['facility_name', 'visit_date'])['min_time_spent']
        
        # Check that each group has only one min value (should be the case)
        multiple_mins = grouped.nunique()[grouped.nunique() > 1]
        
        if len(multiple_mins) > 0:
            logging.warning(f"Found {len(multiple_mins)} facility-date combinations with multiple min values")
            # This might be expected if there are multiple records, but log for investigation
        
        # Check distribution of min_time_spent values
        min_values = df['min_time_spent']
        
        logging.info(f"Min time spent statistics:")
        logging.info(f"  Min: {min_values.min()} minutes")
        logging.info(f"  Max: {min_values.max()} minutes")
        logging.info(f"  Mean: {min_values.mean():.2f} minutes")
        logging.info(f"  Median: {min_values.median():.2f} minutes")
        
        # Check for outliers (values that seem unreasonable)
        very_short_visits = min_values[min_values < 5]  # Less than 5 minutes
        very_long_visits = min_values[min_values > 480]  # More than 8 hours
        
        if len(very_short_visits) > 0:
            logging.warning(f"Found {len(very_short_visits)} visits with min time < 5 minutes")
        
        if len(very_long_visits) > 0:
            logging.warning(f"Found {len(very_long_visits)} visits with min time > 8 hours")
    
    def test_data_completeness_vs_source(self, all_parquet_data, source_data_for_comparison):
        """Test data completeness compared to source data."""
        if source_data_for_comparison.empty:
            pytest.skip("Source data not available for comparison")
        
        parquet_df = all_parquet_data.drop(columns=['_partition_date', '_partition_path', '_file_path'])
        
        # Convert visit_date to same format for comparison
        parquet_df['visit_date'] = pd.to_datetime(parquet_df['visit_date']).dt.date
        source_data_for_comparison['visit_date'] = pd.to_datetime(source_data_for_comparison['visit_date']).dt.date
        
        # Compare record counts by month
        parquet_monthly = parquet_df.groupby(pd.to_datetime(parquet_df['visit_date']).dt.to_period('M')).size()
        source_monthly = source_data_for_comparison.groupby(pd.to_datetime(source_data_for_comparison['visit_date']).dt.to_period('M')).size()
        
        # Check that we have data for the same months
        parquet_months = set(parquet_monthly.index)
        source_months = set(source_monthly.index)
        
        missing_months = source_months - parquet_months
        extra_months = parquet_months - source_months
        
        if missing_months:
            logging.warning(f"Parquet data missing for months: {missing_months}")
        
        if extra_months:
            logging.warning(f"Parquet data has extra months: {extra_months}")
        
        # Compare total record counts (allow some tolerance)
        parquet_total = len(parquet_df)
        source_total = len(source_data_for_comparison)
        
        if source_total > 0:
            completeness_percentage = (parquet_total / source_total) * 100
            logging.info(f"Data completeness: {completeness_percentage:.1f}% "
                        f"({parquet_total}/{source_total} records)")
            
            # Assert reasonable completeness (at least 90%)
            assert completeness_percentage >= 90.0, (
                f"Data completeness too low: {completeness_percentage:.1f}%. "
                f"Expected at least 90%"
            )
            
    def test_partition_record_counts_match_source(self, partition_directories, postgres_connector):
        """Test that each partition has the correct number of records compared to source."""
        count_mismatches = []
        
        for partition_dir in partition_directories:
            partition_date_str = partition_dir.name.replace('partition_date=', '')
            
            try:
                # Parse partition date
                partition_date = datetime.strptime(partition_date_str, '%Y-%m')
                partition_year = partition_date.year
                partition_month = partition_date.month
                
                # Get source count for this month
                source_count_query = f"""
                SELECT COUNT(*) as record_count
                FROM (
                    SELECT 
                        f.facility_name,
                        v.visit_timestamp::date as visit_date,
                        MIN(v.duration_minutes) as min_time_spent
                    FROM visits v
                    JOIN facilities f ON v.facility_id = f.id
                    WHERE v.duration_minutes IS NOT NULL 
                    AND v.visit_timestamp IS NOT NULL
                    AND f.facility_name IS NOT NULL
                    AND EXTRACT(YEAR FROM v.visit_timestamp) = {partition_year}
                    AND EXTRACT(MONTH FROM v.visit_timestamp) = {partition_month}
                    GROUP BY f.facility_name, v.visit_timestamp::date
                ) aggregated_data
                """
                
                with postgres_connector as pg_conn:
                    source_count_result = pg_conn.get_data_sql(source_count_query)
                    source_count = source_count_result.iloc[0]['record_count']
                
                # Get parquet count for this partition
                parquet_files = list(partition_dir.glob("*.parquet"))
                parquet_count = 0
                
                for parquet_file in parquet_files:
                    df = pd.read_parquet(parquet_file)
                    parquet_count += len(df)
                
                # Compare counts
                if source_count != parquet_count:
                    count_mismatches.append({
                        'partition': partition_date_str,
                        'source_count': source_count,
                        'parquet_count': parquet_count,
                        'difference': parquet_count - source_count
                    })
                    
                    logging.warning(f"Partition {partition_date_str}: Count mismatch - "
                                f"Source: {source_count}, Parquet: {parquet_count}, "
                                f"Difference: {parquet_count - source_count}")
                else:
                    logging.info(f"Partition {partition_date_str}: Count match ✅ ({source_count} records)")
                    
            except Exception as e:
                logging.error(f"Count validation failed for partition {partition_date_str}: {e}")
                count_mismatches.append({
                    'partition': partition_date_str,
                    'error': str(e)
                })
        
        assert len(count_mismatches) == 0, (
            f"Significant count mismatches found in {len(count_mismatches)} partitions: {count_mismatches}"
        )
    
    def test_partition_data_completeness(self, partition_directories, postgres_connector):
        """Test that no source records are missing from parquet partitions."""
        missing_data_issues = []
        
        for partition_dir in partition_directories:
            partition_date_str = partition_dir.name.replace('partition_date=', '')
            
            try:
                partition_date = datetime.strptime(partition_date_str, '%Y-%m')
                partition_year = partition_date.year
                partition_month = partition_date.month
                
                # Get source data with unique identifiers
                source_query = f"""
                SELECT 
                    f.facility_name,
                    v.visit_timestamp::date as visit_date,
                    MIN(v.duration_minutes) as min_time_spent
                FROM visits v
                JOIN facilities f ON v.facility_id = f.id
                WHERE v.duration_minutes IS NOT NULL 
                AND v.visit_timestamp IS NOT NULL
                AND f.facility_name IS NOT NULL
                AND EXTRACT(YEAR FROM v.visit_timestamp) = {partition_year}
                AND EXTRACT(MONTH FROM v.visit_timestamp) = {partition_month}
                GROUP BY f.facility_name, v.visit_timestamp::date
                ORDER BY f.facility_name, visit_date
                """
                
                with postgres_connector as pg_conn:
                    source_data = pg_conn.get_data_sql(source_query)
                
                if source_data.empty:
                    logging.info(f"Partition {partition_date_str}: No source data found")
                    continue
                
                # Load parquet data
                parquet_files = list(partition_dir.glob("*.parquet"))
                all_parquet_data = []
                
                for parquet_file in parquet_files:
                    df = pd.read_parquet(parquet_file)
                    all_parquet_data.append(df)
                
                if not all_parquet_data:
                    missing_data_issues.append(f"{partition_date_str}: No parquet files found")
                    continue
                
                combined_parquet_data = pd.concat(all_parquet_data, ignore_index=True)
                
                # Normalize dates for comparison
                source_data['visit_date'] = pd.to_datetime(source_data['visit_date']).dt.date
                combined_parquet_data['visit_date'] = pd.to_datetime(combined_parquet_data['visit_date']).dt.date
                
                # Create unique keys
                source_data['unique_key'] = source_data['facility_name'] + '|' + source_data['visit_date'].astype(str)
                combined_parquet_data['unique_key'] = combined_parquet_data['facility_name'] + '|' + combined_parquet_data['visit_date'].astype(str)
                
                # Find missing records
                source_keys = set(source_data['unique_key'])
                parquet_keys = set(combined_parquet_data['unique_key'])
                missing_keys = source_keys - parquet_keys
                
                if missing_keys:
                    missing_data_issues.append({
                        'partition': partition_date_str,
                        'missing_count': len(missing_keys),
                        'missing_examples': list(missing_keys)[:5]  # First 5 examples
                    })
                    
                    logging.warning(f"Partition {partition_date_str}: {len(missing_keys)} records missing from parquet")
                    for example in list(missing_keys)[:3]:
                        logging.warning(f"  Missing: {example}")
                else:
                    logging.info(f"Partition {partition_date_str}: All source records present in parquet ✅")
                    
            except Exception as e:
                logging.error(f"Completeness check failed for partition {partition_date_str}: {e}")
                missing_data_issues.append(f"{partition_date_str}: ERROR - {str(e)}")
        
        assert len(missing_data_issues) == 0, (
            f"Missing data issues found in {len(missing_data_issues)} partitions: {missing_data_issues}"
        )
    
    def test_partition_value_accuracy(self, partition_directories, postgres_connector):
        """Test that min_time_spent values match between source and parquet."""
        value_accuracy_issues = []
        
        for partition_dir in partition_directories:
            partition_date_str = partition_dir.name.replace('partition_date=', '')
            
            try:
                partition_date = datetime.strptime(partition_date_str, '%Y-%m')
                partition_year = partition_date.year
                partition_month = partition_date.month
                
                # Get source data
                source_query = f"""
                SELECT 
                    f.facility_name,
                    v.visit_timestamp::date as visit_date,
                    MIN(v.duration_minutes) as min_time_spent
                FROM visits v
                JOIN facilities f ON v.facility_id = f.id
                WHERE v.duration_minutes IS NOT NULL 
                AND v.visit_timestamp IS NOT NULL
                AND f.facility_name IS NOT NULL
                AND EXTRACT(YEAR FROM v.visit_timestamp) = {partition_year}
                AND EXTRACT(MONTH FROM v.visit_timestamp) = {partition_month}
                GROUP BY f.facility_name, v.visit_timestamp::date
                """
                
                with postgres_connector as pg_conn:
                    source_data = pg_conn.get_data_sql(source_query)
                
                if source_data.empty:
                    continue
                
                # Load parquet data
                parquet_files = list(partition_dir.glob("*.parquet"))
                all_parquet_data = []
                
                for parquet_file in parquet_files:
                    df = pd.read_parquet(parquet_file)
                    all_parquet_data.append(df)
                
                if not all_parquet_data:
                    continue
                
                combined_parquet_data = pd.concat(all_parquet_data, ignore_index=True)
                
                # Prepare for comparison
                source_data['visit_date'] = pd.to_datetime(source_data['visit_date']).dt.date
                combined_parquet_data['visit_date'] = pd.to_datetime(combined_parquet_data['visit_date']).dt.date
                
                # Merge on facility_name and visit_date
                merged_data = pd.merge(
                    source_data,
                    combined_parquet_data,
                    on=['facility_name', 'visit_date'],
                    how='inner',
                    suffixes=('_source', '_parquet')
                )
                
                # Find value mismatches
                tolerance = 0.01  
                mismatches = merged_data[abs(merged_data['min_time_spent_source'] - merged_data['min_time_spent_parquet']) > tolerance]
                
                if not mismatches.empty:
                    value_accuracy_issues.append({
                        'partition': partition_date_str,
                        'mismatch_count': len(mismatches),
                        'total_compared': len(merged_data),
                        'accuracy_percentage': ((len(merged_data) - len(mismatches)) / len(merged_data)) * 100,
                        'examples': mismatches[['facility_name', 'visit_date', 'min_time_spent_source', 'min_time_spent_parquet']].head(3).to_dict('records')
                    })
                    
                    logging.warning(f"Partition {partition_date_str}: {len(mismatches)} value mismatches out of {len(merged_data)} records")
                    for _, row in mismatches.head(3).iterrows():
                        logging.warning(f"  Mismatch: {row['facility_name']} on {row['visit_date']} - "
                                    f"Source: {row['min_time_spent_source']}, Parquet: {row['min_time_spent_parquet']}")
                else:
                    logging.info(f"Partition {partition_date_str}: All values match ✅ ({len(merged_data)} records)")
                    
            except Exception as e:
                logging.error(f"Value accuracy check failed for partition {partition_date_str}: {e}")
                value_accuracy_issues.append(f"{partition_date_str}: ERROR - {str(e)}")
        
        assert len(value_accuracy_issues) == 0, (
            f"Value accuracy issues found in {len(value_accuracy_issues)} partitions: {value_accuracy_issues}"
        )
    
    def test_partition_performance_benchmark(self, partition_directories):
        """Test that partition files can be read within reasonable time."""
        import time
        
        slow_files = []
        total_read_time = 0
        
        for partition_dir in partition_directories:
            parquet_files = list(partition_dir.glob("*.parquet"))
            
            for parquet_file in parquet_files:
                start_time = time.time()
                try:
                    df = pd.read_parquet(parquet_file)
                    read_time = time.time() - start_time
                    total_read_time += read_time
                    
                    # Flag files that take more than 5 seconds to read
                    if read_time > 5.0:
                        slow_files.append(f"{parquet_file}: {read_time:.2f}s")
                        
                except Exception as e:
                    logging.error(f"Performance test failed for {parquet_file}: {e}")
        
        if slow_files:
            logging.warning(f"Found {len(slow_files)} slow-reading files: {slow_files}")
        
        logging.info(f"Total read time for all partitions: {total_read_time:.2f}s")
        
        # Assert that average read time per file is reasonable
        total_files = sum(len(list(pd.glob("*.parquet"))) for pd in partition_directories)
        if total_files > 0:
            avg_read_time = total_read_time / total_files
            assert avg_read_time < 10.0, (
                f"Average file read time too slow: {avg_read_time:.2f}s per file"
            )
    
    def test_generate_partition_summary_report(self, partition_directories, all_parquet_data):
        """Generate a comprehensive summary report of the partitioned data."""
        summary = {
            'total_partitions': len(partition_directories),
            'total_records': len(all_parquet_data),
            'date_range': {},
            'facility_count': 0,
            'partition_details': []
        }
        
        # Calculate date range
        if not all_parquet_data.empty:
            visit_dates = pd.to_datetime(all_parquet_data['visit_date'])
            summary['date_range'] = {
                'min_date': visit_dates.min().strftime('%Y-%m-%d'),
                'max_date': visit_dates.max().strftime('%Y-%m-%d')
            }
            summary['facility_count'] = all_parquet_data['facility_name'].nunique()
        
        # Partition details
        for partition_dir in partition_directories:
            partition_data = all_parquet_data[all_parquet_data['_partition_path'] == str(partition_dir)]
            
            summary['partition_details'].append({
                'partition_name': partition_dir.name,
                'record_count': len(partition_data),
                'facility_count': partition_data['facility_name'].nunique() if not partition_data.empty else 0,
                'file_count': len(list(partition_dir.glob("*.parquet")))
            })
        
        # Log summary
        logging.info("=" * 80)
        logging.info("FACILITY NAME MIN TIME SPENT PARTITION SUMMARY")
        logging.info("=" * 80)
        logging.info(f"Total Partitions: {summary['total_partitions']}")
        logging.info(f"Total Records: {summary['total_records']:,}")
        logging.info(f"Unique Facilities: {summary['facility_count']}")
        logging.info(f"Date Range: {summary['date_range'].get('min_date', 'N/A')} to {summary['date_range'].get('max_date', 'N/A')}")
        logging.info("=" * 80)
        
        return summary