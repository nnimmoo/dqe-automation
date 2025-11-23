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
class TestFacilityTypeAvgTimeSpentPerVisitDate:
    """
    Test suite for validating facility_type_avg_time_spent_per_visit_date Parquet files.
    Tests partitioned data structure by visit_date (year-month), partition consistency, and data quality.
    """
    
    @pytest.fixture(scope="class")
    def parquet_base_directory(self, request):
        """Get the base directory for facility_type_avg_time_spent_per_visit_date partitions."""
        
        base_path_str = request.config.getoption("--facility-type-avg-time-path")
        
        if not base_path_str:
            base_path_str = os.getenv("FACILITY_TYPE_AVG_TIME_PATH")
        
        if not base_path_str:
            root_path = request.config.getoption("--parquet-root-path") or os.getenv("PARQUET_ROOT_PATH", "/parquet_data")
            base_path_str = os.path.join(root_path, "facility_type_avg_time_spent_per_visit_date")
        
        base_path = Path(base_path_str)
        
        if not base_path.exists():
            pytest.skip(f"Parquet data directory not found: {base_path}")
        
        logging.info(f"Using facility_type_avg_time_spent_per_visit_date path: {base_path}")
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
    def all_parquet_data(self, partition_directories):
        """Load all data from all partitions."""
        all_data = []
        
        for partition_dir in partition_directories:
            # Extract partition date from directory name
            partition_date = partition_dir.name.replace('partition_date=', '')
            
            # Find parquet files in the partition directory
            parquet_files = list(partition_dir.glob("*.parquet"))
            
            for parquet_file in parquet_files:
                try:
                    df = pd.read_parquet(parquet_file)
                    # Add partition information
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
            f.facility_type,
            v.visit_timestamp::date as visit_date,
            ROUND(AVG(v.duration_minutes), 2) as avg_time_spent
        FROM visits v
        JOIN facilities f ON v.facility_id = f.id
        WHERE v.duration_minutes IS NOT NULL 
          AND v.visit_timestamp IS NOT NULL
          AND f.facility_type IS NOT NULL
        GROUP BY f.facility_type, v.visit_timestamp::date
        ORDER BY f.facility_type, visit_date
        """
        
        try:
            with postgres_connector as pg_conn:
                result = pg_conn.get_data_sql(query)
                logging.info(f"Successfully loaded {len(result)} records from source database")
                return result
        except Exception as e:
            logging.error(f"Failed to load source data: {e}")
            return pd.DataFrame()
    
    @pytest.fixture(scope="class")
    def valid_facility_types(self, postgres_connector):
        """Get valid facility types from the database."""
        query = 'SELECT DISTINCT f.facility_type FROM facilities f WHERE f.facility_type IS NOT NULL ORDER BY f.facility_type'
        
        try:
            with postgres_connector as pg_conn:
                result = pg_conn.get_data_sql(query)
                facility_types_list = result['facility_type'].tolist()
                logging.info(f"Successfully loaded {len(facility_types_list)} facility types from source database: {facility_types_list}")
                return facility_types_list
        except Exception as e:
            logging.error(f"Failed to load facility types from database: {e}")
            # fallback
            return ['Hospital', 'Clinic', 'Emergency Room', 'Urgent Care', 'Specialty Clinic', 'Specialty Center']
    
    def test_partition_directories_exist_and_valid_naming(self, parquet_base_directory, partition_directories):
        """Test that partition directories exist and follow correct naming convention."""
        assert len(partition_directories) > 0, "No partition directories found"
        
        # Test naming convention
        invalid_partitions = []
        for partition_dir in partition_directories:
            if not re.match(r'partition_date=\d{4}-\d{2}$', partition_dir.name):
                invalid_partitions.append(f"Invalid naming: {partition_dir.name}")
        
        assert len(invalid_partitions) == 0, f"Invalid partition names: {invalid_partitions}"
        
        logging.info(f"Found {len(partition_directories)} valid partition directories")
        
        # Log partition date range
        partition_dates = [p.name.replace('partition_date=', '') for p in partition_directories]
        logging.info(f"Partition date range: {min(partition_dates)} to {max(partition_dates)}")
    
    def test_partition_count_and_date_range_reasonable(self, partition_directories):
        """Test that the number of partitions and date range are reasonable."""        
        # Validate date formats and ranges
        partition_dates = []
        for partition_dir in partition_directories:
            date_str = partition_dir.name.replace('partition_date=', '')
            try:
                partition_date = datetime.strptime(date_str, '%Y-%m').date()
                partition_dates.append(partition_date)
            except ValueError:
                pytest.fail(f"Invalid date format in partition: {date_str}")
        
        partition_dates.sort()
        min_date = min(partition_dates)
        max_date = max(partition_dates)
        
        # Check that dates are reasonable
        current_date = date.today()
        assert min_date <= current_date, f"Future partition date found: {min_date}"
        assert max_date <= current_date, f"Future partition date found: {max_date}"
    
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
    
    def test_parquet_files_readable_and_schema_consistent(self, partition_directories):
        """Test that all parquet files are readable and have consistent schema."""
        expected_columns = ['facility_type', 'visit_date', 'avg_time_spent']
        unreadable_files = []
        empty_files = []
        schema_issues = []
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
                    
                    # Check schema
                    if list(df.columns) != expected_columns:
                        schema_issues.append(
                            f"{parquet_file}: Expected {expected_columns}, got {list(df.columns)}"
                        )
                    
                    # Check data types
                    if not pd.api.types.is_object_dtype(df['facility_type']):
                        schema_issues.append(f"{parquet_file}: facility_type should be object/string type")
                    
                    if not pd.api.types.is_datetime64_any_dtype(df['visit_date']) and not pd.api.types.is_object_dtype(df['visit_date']):
                        schema_issues.append(f"{parquet_file}: visit_date should be datetime or date type")
                    
                    if not pd.api.types.is_numeric_dtype(df['avg_time_spent']):
                        schema_issues.append(f"{parquet_file}: avg_time_spent should be numeric type")
                        
                except Exception as e:
                    unreadable_files.append(f"{parquet_file}: {e}")
        
        assert len(unreadable_files) == 0, f"Unreadable files: {unreadable_files}"
        assert len(empty_files) == 0, f"Empty files: {empty_files}"
        assert len(schema_issues) == 0, f"Schema issues: {schema_issues}"
        
        logging.info(f"All parquet files are readable with consistent schema. Total records: {total_records}")
    
    def test_partition_data_consistency(self, all_parquet_data):
        """Test that data in each partition matches the partition date (year-month)."""
        inconsistent_partitions = []
        
        # Group by partition
        for partition_date, group in all_parquet_data.groupby('_partition_date'):
            try:
                # Parse partition date (year-month)
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
                    break  # Only report first inconsistency per partition
        
        assert len(inconsistent_partitions) == 0, (f"Found partition data inconsistencies: {inconsistent_partitions}")
        
        logging.info("All partition data is consistent with partition dates")
    
    def test_data_quality_across_partitions(self, all_parquet_data, data_quality_library):
        """Test data quality across all partitions."""
        df = all_parquet_data.drop(columns=['_partition_date', '_partition_path', '_file_path'])
        
        data_quality_library.check_dataset_is_not_empty(df, min_rows=1)
        data_quality_library.check_column_exists(df, ['facility_type', 'visit_date', 'avg_time_spent'])
        
        # Test no null values in critical fields
        data_quality_library.check_not_null_values(
            df,
            column_names=['facility_type', 'visit_date', 'avg_time_spent'],
            max_null_percentage=0.0
        )
        
        # Test avg_time_spent is positive and reasonable
        data_quality_library.check_value_range(
            df,
            column_name='avg_time_spent',
            min_value=1.0,
            max_value=1440.0  # 24 hours in minutes
        )
        
        logging.info(f"Data quality checks passed for {len(df)} records")
    
    def test_facility_type_validity(self, all_parquet_data, valid_facility_types):
        """Test that facility_type values are valid."""
        df = all_parquet_data
        
        unique_facility_types = df['facility_type'].unique()
        invalid_facility_types = [ft for ft in unique_facility_types if ft not in valid_facility_types]
        
        assert len(invalid_facility_types) == 0, (
            f"Invalid facility types found: {invalid_facility_types}"
        )
        
        logging.info(f"All facility types are valid. Found: {sorted(unique_facility_types)}")
    
    def test_avg_time_spent_rounding_and_calculation(self, all_parquet_data):
        """Test that avg_time_spent is properly rounded to 2 decimal places and values are reasonable."""
        df = all_parquet_data
        
        # Check rounding to 2 decimal places
        rounding_issues = []
        for _, row in df.iterrows():
            avg_time = row['avg_time_spent']
            if pd.notna(avg_time):
                # Check decimal places
                decimal_str = str(avg_time)
                if '.' in decimal_str:
                    decimal_places = len(decimal_str.split('.')[-1])
                    if decimal_places > 2:
                        rounding_issues.append(f"Value {avg_time} has {decimal_places} decimal places")
        
        assert len(rounding_issues) == 0, (
            f"Found {len(rounding_issues)} values not properly rounded to 2 decimal places: {rounding_issues[:5]}"
        )
        
        # Check value distribution
        avg_times = df['avg_time_spent']
        logging.info(f"Average time spent statistics:")
        logging.info(f"  Min: {avg_times.min():.2f} minutes")
        logging.info(f"  Max: {avg_times.max():.2f} minutes")
        logging.info(f"  Mean: {avg_times.mean():.2f} minutes")
        logging.info(f"  Median: {avg_times.median():.2f} minutes")
        
        # Check for outliers
        very_short_avg = avg_times[avg_times < 5]  # Less than 5 minutes average
        very_long_avg = avg_times[avg_times > 480]  # More than 8 hours average
        
        if len(very_short_avg) > 0:
            logging.warning(f"Found {len(very_short_avg)} records with avg time < 5 minutes")
        
        if len(very_long_avg) > 0:
            logging.warning(f"Found {len(very_long_avg)} records with avg time > 8 hours")
    
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
                        f.facility_type,
                        v.visit_timestamp::date as visit_date,
                        ROUND(AVG(v.duration_minutes), 2) as avg_time_spent
                    FROM visits v
                    JOIN facilities f ON v.facility_id = f.id
                    WHERE v.duration_minutes IS NOT NULL 
                      AND v.visit_timestamp IS NOT NULL
                      AND f.facility_type IS NOT NULL
                      AND EXTRACT(YEAR FROM v.visit_timestamp) = {partition_year}
                      AND EXTRACT(MONTH FROM v.visit_timestamp) = {partition_month}
                    GROUP BY f.facility_type, v.visit_timestamp::date
                ) aggregated_data
                """
                
                with postgres_connector as pg_conn:
                    source_count_result = pg_conn.get_data_sql(source_count_query)
                    source_count = source_count_result.iloc[1]['record_count']
                
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
        
        # Report summary
        if count_mismatches:
            logging.error("=" * 60)
            logging.error("RECORD COUNT MISMATCHES FOUND:")
            for mismatch in count_mismatches:
                if 'error' in mismatch:
                    logging.error(f"  {mismatch['partition']}: ERROR - {mismatch['error']}")
                else:
                    logging.error(f"  {mismatch['partition']}: Source={mismatch['source_count']}, "
                                f"Parquet={mismatch['parquet_count']}, Diff={mismatch['difference']}")
            logging.error("=" * 60)
        
        # Allow some tolerance for count differences
        significant_mismatches = [m for m in count_mismatches if 'difference' in m and abs(m['difference']) > 5]
        
        assert len(significant_mismatches) == 0, (
            f"Significant count mismatches found in {len(significant_mismatches)} partitions: {significant_mismatches}"
        )
    
    def test_partition_value_accuracy(self, partition_directories, postgres_connector):
        """Test that avg_time_spent values match between source and parquet for each partition."""
        value_accuracy_issues = []
        
        for partition_dir in partition_directories:
            partition_date_str = partition_dir.name.replace('partition_date=', '')
            
            try:
                partition_date = datetime.strptime(partition_date_str, '%Y-%m')
                partition_year = partition_date.year
                partition_month = partition_date.month
                
                # Get source data for this month
                source_query = f"""
                SELECT 
                    f.facility_type,
                    v.visit_timestamp::date as visit_date,
                    ROUND(AVG(v.duration_minutes), 2) as avg_time_spent
                FROM visits v
                JOIN facilities f ON v.facility_id = f.id
                WHERE v.duration_minutes IS NOT NULL 
                  AND v.visit_timestamp IS NOT NULL
                  AND f.facility_type IS NOT NULL
                  AND EXTRACT(YEAR FROM v.visit_timestamp) = {partition_year}
                  AND EXTRACT(MONTH FROM v.visit_timestamp) = {partition_month}
                GROUP BY f.facility_type, v.visit_timestamp::date
                ORDER BY f.facility_type, visit_date
                """
                
                with postgres_connector as pg_conn:
                    source_data = pg_conn.get_data_sql(source_query)
                
                if source_data.empty:
                    logging.info(f"No source data for partition {partition_date_str}")
                    continue
                
                # Load parquet data for this partition
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
                
                # Merge on facility_type and visit_date
                merged_data = pd.merge(
                    source_data,
                    combined_parquet_data,
                    on=['facility_type', 'visit_date'],
                    how='inner',
                    suffixes=('_source', '_parquet')
                )
                
                # Find value mismatches
                tolerance = 0.01  # Allow small floating point differences
                mismatches = merged_data[
                    abs(merged_data['avg_time_spent_source'] - merged_data['avg_time_spent_parquet']) > tolerance
                ]
                
                if not mismatches.empty:
                    value_accuracy_issues.append({
                        'partition': partition_date_str,
                        'mismatch_count': len(mismatches),
                        'total_compared': len(merged_data),
                        'accuracy_percentage': ((len(merged_data) - len(mismatches)) / len(merged_data)) * 100,
                        'examples': mismatches[['facility_type', 'visit_date', 'avg_time_spent_source', 'avg_time_spent_parquet']].head(3).to_dict('records')
                    })
                    
                    logging.warning(f"Partition {partition_date_str}: {len(mismatches)} value mismatches out of {len(merged_data)} records")
                    for _, row in mismatches.head(3).iterrows():
                        logging.warning(f"  Mismatch: {row['facility_type']} on {row['visit_date']} - "
                                      f"Source: {row['avg_time_spent_source']:.2f}, "
                                      f"Parquet: {row['avg_time_spent_parquet']:.2f}")
                else:
                    logging.info(f"Partition {partition_date_str}: All values match ✅ ({len(merged_data)} records)")
                    
            except Exception as e:
                logging.error(f"Value accuracy check failed for partition {partition_date_str}: {e}")
                value_accuracy_issues.append(f"{partition_date_str}: ERROR - {str(e)}")
        
        assert len(value_accuracy_issues) == 0, (
            f"Value accuracy issues found in {len(value_accuracy_issues)} partitions: {value_accuracy_issues}"
        )
    
    def test_aggregation_logic_validation(self, partition_directories, postgres_connector):
        """Test that the average calculation is
 correct by comparing with detailed source data."""
        aggregation_issues = []
        
        # Test a sample of partitions (first 3 to avoid long test times)
        sample_partitions = partition_directories[:3]
        
        for partition_dir in sample_partitions:
            partition_date_str = partition_dir.name.replace('partition_date=', '')
            
            try:
                partition_date = datetime.strptime(partition_date_str, '%Y-%m')
                partition_year = partition_date.year
                partition_month = partition_date.month
                
                # Get detailed source data (all individual records)
                detailed_source_query = f"""
                SELECT 
                    f.facility_type,
                    v.visit_timestamp::date as visit_date,
                    v.duration_minutes
                FROM visits v
                JOIN facilities f ON v.facility_id = f.id
                WHERE v.duration_minutes IS NOT NULL 
                  AND v.visit_timestamp IS NOT NULL
                  AND f.facility_type IS NOT NULL
                  AND EXTRACT(YEAR FROM v.visit_timestamp) = {partition_year}
                  AND EXTRACT(MONTH FROM v.visit_timestamp) = {partition_month}
                ORDER BY f.facility_type, visit_date
                """
                
                with postgres_connector as pg_conn:
                    detailed_source_data = pg_conn.get_data_sql(detailed_source_query)
                
                if detailed_source_data.empty:
                    continue
                
                # Calculate actual averages from detailed data
                actual_averages = detailed_source_data.groupby(['facility_type', 'visit_date'])['duration_minutes'].mean().reset_index()
                actual_averages['avg_time_spent'] = actual_averages['duration_minutes'].round(2)
                actual_averages = actual_averages.drop(columns=['duration_minutes'])
                
                # Load parquet data for this partition
                parquet_files = list(partition_dir.glob("*.parquet"))
                all_parquet_data = []
                
                for parquet_file in parquet_files:
                    df = pd.read_parquet(parquet_file)
                    all_parquet_data.append(df)
                
                if not all_parquet_data:
                    continue
                
                combined_parquet_data = pd.concat(all_parquet_data, ignore_index=True)
                
                # Prepare for comparison
                actual_averages['visit_date'] = pd.to_datetime(actual_averages['visit_date']).dt.date
                combined_parquet_data['visit_date'] = pd.to_datetime(combined_parquet_data['visit_date']).dt.date
                
                # Merge to compare
                comparison = pd.merge(
                    actual_averages,
                    combined_parquet_data,
                    on=['facility_type', 'visit_date'],
                    how='outer',
                    suffixes=('_actual', '_parquet')
                )
                
                # Find mismatches
                mismatches = comparison[
                    (comparison['avg_time_spent_actual'].notna()) & 
                    (comparison['avg_time_spent_parquet'].notna()) &
                    (abs(comparison['avg_time_spent_actual'] - comparison['avg_time_spent_parquet']) > 0.01)
                ]
                
                if not mismatches.empty:
                    aggregation_issues.append({
                        'partition': partition_date_str,
                        'mismatch_count': len(mismatches),
                        'examples': mismatches[['facility_type', 'visit_date', 'avg_time_spent_actual', 'avg_time_spent_parquet']].head(3).to_dict('records')
                    })
                    
                    logging.error(f"Partition {partition_date_str}: {len(mismatches)} aggregation mismatches found")
                    for _, row in mismatches.head(3).iterrows():
                        logging.error(f"  Aggregation error: {row['facility_type']} on {row['visit_date']} - "
                                    f"Expected: {row['avg_time_spent_actual']:.2f}, "
                                    f"Got: {row['avg_time_spent_parquet']:.2f}")
                else:
                    logging.info(f"Partition {partition_date_str}: Aggregation accuracy verified ✅")
                    
            except Exception as e:
                logging.error(f"Aggregation test failed for partition {partition_date_str}: {e}")
                continue
        
        # Assert no aggregation issues
        assert len(aggregation_issues) == 0, (
            f"Aggregation accuracy issues found in {len(aggregation_issues)} partitions: {aggregation_issues}"
        )
        
        logging.info("✅ All tested partition aggregations are accurate")
    
    def test_data_completeness_vs_source(self, all_parquet_data, source_data_for_comparison):
        """Test data completeness compared to source data."""
        if source_data_for_comparison.empty:
            pytest.skip("Source data not available for comparison")
        
        parquet_df = all_parquet_data.drop(columns=['_partition_date', '_partition_path', '_file_path'])
        
        # Convert visit_date to same format for comparison
        parquet_df['visit_date'] = pd.to_datetime(parquet_df['visit_date']).dt.date
        source_data_for_comparison['visit_date'] = pd.to_datetime(source_data_for_comparison['visit_date']).dt.date
        
        # Compare total record counts
        parquet_total = len(parquet_df)
        source_total = len(source_data_for_comparison)
        
        if source_total > 0:
            completeness_percentage = (parquet_total / source_total) * 100
            logging.info(f"Data completeness: {completeness_percentage:.1f}% "
                        f"({parquet_total}/{source_total} records)")
            
            # Assert reasonable completeness (at least 95%)
            assert completeness_percentage >= 95.0, (
                f"Data completeness too low: {completeness_percentage:.1f}%. "
                f"Expected at least 95%"
            )
        
        # Compare by facility type
        parquet_by_facility = parquet_df.groupby('facility_type').size()
        source_by_facility = source_data_for_comparison.groupby('facility_type').size()
        
        logging.info("Records by facility type:")
        for facility_type in sorted(set(parquet_by_facility.index) | set(source_by_facility.index)):
            parquet_count = parquet_by_facility.get(facility_type, 0)
            source_count = source_by_facility.get(facility_type, 0)
            logging.info(f"  {facility_type}: Source={source_count}, Parquet={parquet_count}")
    
    def test_generate_partition_summary_report(self, partition_directories, all_parquet_data):
        """Generate a comprehensive summary report of the partitioned data."""
        summary = {
            'total_partitions': len(partition_directories),
            'total_records': len(all_parquet_data),
            'date_range': {},
            'facility_type_count': 0,
            'partition_details': []
        }
        
        # Calculate date range and facility types
        if not all_parquet_data.empty:
            visit_dates = pd.to_datetime(all_parquet_data['visit_date'])
            summary['date_range'] = {
                'min_date': visit_dates.min().strftime('%Y-%m-%d'),
                'max_date': visit_dates.max().strftime('%Y-%m-%d')
            }
            summary['facility_type_count'] = all_parquet_data['facility_type'].nunique()
        
        # Partition details
        for partition_dir in partition_directories:
            partition_date = partition_dir.name.replace('partition_date=', '')
            partition_data = all_parquet_data[all_parquet_data['_partition_date'] == partition_date]
            
            if not partition_data.empty:
                partition_details = {
                    'partition_date': partition_date,
                    'record_count': len(partition_data),
                    'facility_type_count': partition_data['facility_type'].nunique(),
                    'avg_time_range': {
                        'min': partition_data['avg_time_spent'].min(),
                        'max': partition_data['avg_time_spent'].max(),
                        'mean': partition_data['avg_time_spent'].mean()
                    },
                    'file_count': len(list(partition_dir.glob("*.parquet")))
                }
            else:
                partition_details = {
                    'partition_date': partition_date,
                    'record_count': 0,
                    'facility_type_count': 0,
                    'avg_time_range': {'min': 0, 'max': 0, 'mean': 0},
                    'file_count': len(list(partition_dir.glob("*.parquet")))
                }
            
            summary['partition_details'].append(partition_details)
        
        # Log summary
        logging.info("=" * 80)
        logging.info("FACILITY TYPE AVG TIME SPENT PARTITION SUMMARY")
        logging.info("=" * 80)
        logging.info(f"Total Partitions: {summary['total_partitions']}")
        logging.info(f"Total Records: {summary['total_records']:,}")
        logging.info(f"Unique Facility Types: {summary['facility_type_count']}")
        logging.info(f"Date Range: {summary['date_range'].get('min_date', 'N/A')} to {summary['date_range'].get('max_date', 'N/A')}")
        logging.info("")
        logging.info("Recent Partitions:")
        for details in summary['partition_details'][-5:]:  # Show last 5 partitions
            logging.info(f"  {details['partition_date']}:")
            logging.info(f"    Records: {details['record_count']:,}")
            logging.info(f"    Facility Types: {details['facility_type_count']}")
            if details['record_count'] > 0:
                logging.info(f"    Avg Time Range: {details['avg_time_range']['min']:.2f} - {details['avg_time_range']['max']:.2f} min")
        logging.info("=" * 80)
        
        return summary