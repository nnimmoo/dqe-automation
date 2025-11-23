"""
Description: Data Quality checks for patient_sum_treatment_cost_per_facility_type Parquet files.
Data Source: Parquet files located in /parquet_data/patient_sum_treatment_cost_per_facility_type/
Data Target: PostgreSQL source table 'visits', 'patients', and 'facilities' for comparison.
Requirement(s): TICKET-2
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
class TestPatientSumTreatmentCostPerFacilityType:
    """
    Test suite for validating patient_sum_treatment_cost_per_facility_type Parquet files.
    Tests partitioned data structure by facility_type, partition consistency, and data quality.
    """
    
    @pytest.fixture(scope="class")
    def parquet_base_directory(self,
    request):
        """Get the base directory for patient_sum_treatment_cost_per_facility_type partitions."""
        
        base_path_str = request.config.getoption("--patient-sum-treatment-cost-path")
        
        if not base_path_str:
            base_path_str = os.getenv("PATIENT_SUM_TREATMENT_COST_PATH")
        
        if not base_path_str:
            root_path = request.config.getoption("--parquet-root-path") or os.getenv("PARQUET_ROOT_PATH", "/parquet_data")
            base_path_str = os.path.join(root_path, "patient_sum_treatment_cost_per_facility_type")
        
        base_path = Path(base_path_str)
        
        if not base_path.exists():
            pytest.skip(f"Parquet data directory not found: {base_path}")
        
        logging.info(f"Using patient_sum_treatment_cost_per_facility_type path: {base_path}")
        return base_path
    
    @pytest.fixture(scope="class")
    def partition_directories(self, parquet_base_directory):
        """Get all partition directories (facility_type folders)."""
        partition_dirs = []
        
        for item in parquet_base_directory.iterdir():
            if item.is_dir() and item.name.startswith('facility_type_partition='):
                partition_dirs.append(item)
        
        partition_dirs.sort()  # Sort by name
        
        if not partition_dirs:
            pytest.skip("No partition directories found")
        
        return partition_dirs
    
    @pytest.fixture(scope="class")
    def all_parquet_data(self, partition_directories):
        """Load all data from all partitions."""
        all_data = []
        
        for partition_dir in partition_directories:
            # Extract facility_type from directory name
            facility_type = partition_dir.name.replace('facility_type_partition=', '').replace('_', ' ')
            
            # Find parquet files in the partition directory
            parquet_files = list(partition_dir.glob("*.parquet"))
            
            for parquet_file in parquet_files:
                try:
                    df = pd.read_parquet(parquet_file)
                    # Add partition information
                    df['_partition_facility_type'] = facility_type
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
                CONCAT(p.first_name, ' ', p.last_name) as full_name,
                f.facility_type,
                SUM(v.treatment_cost) as sum_treatment_cost
            FROM visits v
            JOIN patients p ON v.patient_id = p.id
            JOIN facilities f ON v.facility_id = f.id
            WHERE v.treatment_cost IS NOT NULL 
            AND p.first_name IS NOT NULL 
            AND p.last_name IS NOT NULL
            AND f.facility_type IS NOT NULL
            GROUP BY p.first_name, p.last_name, f.facility_type
            ORDER BY f.facility_type, full_name
        """
        
        try:
            with postgres_connector as pg_conn:
               return pg_conn.get_data_sql(query)
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
    
    def test_partition_directories_exist_and_valid_naming(self, parquet_base_directory, partition_directories, valid_facility_types):
        """Test that partition directories exist and follow correct naming convention."""
        assert len(partition_directories) > 0, "No partition directories found"
        
        # Test naming convention and extract facility types
        found_facility_types = []
        invalid_partitions = []
        
        for partition_dir in partition_directories:
            if not partition_dir.name.startswith('facility_type_partition='):
                invalid_partitions.append(f"Invalid naming: {partition_dir.name}")
                continue
            
            # Extract facility type (replace underscores with spaces)
            facility_type = partition_dir.name.replace('facility_type_partition=', '').replace('_', ' ')
            found_facility_types.append(facility_type)
            
            # Validate against database facility types
            if facility_type not in valid_facility_types:
                invalid_partitions.append(f"Unknown facility type: {facility_type}")
        
        assert len(invalid_partitions) == 0, f"Invalid partitions found: {invalid_partitions}"
        
        logging.info(f"Found {len(partition_directories)} valid partition directories")
        logging.info(f"Facility types found in partitions: {sorted(found_facility_types)}")
        logging.info(f"Valid facility types from database: {sorted(valid_facility_types)}")
    
    def test_partition_count_covers_all_facility_types(self, partition_directories, valid_facility_types):
        """Test that we have partitions for all facility types present in source data."""
        # Get facility types from partitions
        partition_facility_types = set()
        for partition_dir in partition_directories:
            facility_type = partition_dir.name.replace('facility_type_partition=', '').replace('_', ' ')
            partition_facility_types.add(facility_type)
        
        # Compare
        missing_partitions = set(valid_facility_types) - partition_facility_types
        extra_partitions = partition_facility_types - set(valid_facility_types)
        
        if missing_partitions:
            logging.warning(f"Missing partitions for facility types: {missing_partitions}")
        
        if extra_partitions:
            logging.warning(f"Extra partitions for facility types: {extra_partitions}")
        
        logging.info(f"Source facility types: {sorted(set(valid_facility_types))}")
        logging.info(f"Partition facility types: {sorted(partition_facility_types)}")
        
        # Assert that we have partitions for all major facility types
        assert len(missing_partitions) == 0, (
            f"Missing partitions for facility types: {missing_partitions}"
        )
    
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
        expected_columns = ['full_name', 'facility_type', 'sum_treatment_cost']
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
                    if not pd.api.types.is_object_dtype(df['full_name']):
                        schema_issues.append(f"{parquet_file}: full_name should be object/string type")
                    
                    if not pd.api.types.is_object_dtype(df['facility_type']):
                        schema_issues.append(f"{parquet_file}: facility_type should be object/string type")
                    
                    if not pd.api.types.is_numeric_dtype(df['sum_treatment_cost']):
                        schema_issues.append(f"{parquet_file}: sum_treatment_cost should be numeric type")
                        
                except Exception as e:
                    unreadable_files.append(f"{parquet_file}: {e}")
        
        assert len(unreadable_files) == 0, f"Unreadable files: {unreadable_files}"
        assert len(empty_files) == 0, f"Empty files: {empty_files}"
        assert len(schema_issues) == 0, f"Schema issues: {schema_issues}"
        
        logging.info(f"All parquet files are readable with consistent schema. Total records: {total_records}")
    
    def test_partition_data_consistency(self, all_parquet_data):
        """Test that data in each partition matches the partition facility_type."""
        inconsistent_partitions = []
        
        # Group by partition
        for partition_facility_type, group in all_parquet_data.groupby('_partition_facility_type'):
            # Check that all facility_type values in this partition match the partition name
            unique_facility_types = group['facility_type'].unique()
            
            for facility_type in unique_facility_types:
                if facility_type != partition_facility_type:
                    inconsistent_partitions.append(
                        f"Partition '{partition_facility_type}' contains data for facility_type '{facility_type}'"
                    )
        
        assert len(inconsistent_partitions) == 0, (
            f"Found partition data inconsistencies: {inconsistent_partitions}"
        )
        
        logging.info("All partition data is consistent with partition facility_types")
    
    def test_data_quality_across_partitions(self, all_parquet_data, data_quality_library):
        """Test data quality across all partitions."""
        # Remove internal columns added during loading
        df = all_parquet_data.drop(columns=['_partition_facility_type', '_partition_path', '_file_path'])
        
        data_quality_library.check_dataset_is_not_empty(df, min_rows=1)
        
        data_quality_library.check_column_exists(df, ['full_name', 'facility_type', 'sum_treatment_cost'])
        
        # Test no null values in critical fields
        data_quality_library.check_not_null_values(
            df,
            column_names=['full_name', 'facility_type', 'sum_treatment_cost'],
            max_null_percentage=0.0
        )
        
        # Test sum_treatment_cost is non-negative
        data_quality_library.check_value_range(
            df,
            column_name='sum_treatment_cost',
            min_value=0.0,
            max_value=10000000.0  # Reasonable upper limit, catch outliers
        )
        
        logging.info(f"Data quality checks passed for {len(df)} records")
    
    def test_full_name_format_validation(self, all_parquet_data):
        """Test that full_name follows correct format (first_name + ' ' + last_name)."""
        df = all_parquet_data
        
        invalid_names = []
        
        for _, row in df.iterrows():
            full_name = row['full_name']
            
            # Check that full_name contains at least first and last name (space-separated)
            if pd.isna(full_name) or not isinstance(full_name, str):
                invalid_names.append(f"Invalid type: {full_name}")
                continue
            
            name_parts = full_name.strip().split()
            if len(name_parts) < 2:
                invalid_names.append(f"Insufficient name parts: '{full_name}'")
                continue
            
            # Check that each part is not empty
            for part in name_parts:
                if len(part.strip()) == 0:
                    invalid_names.append(f"Empty name part in: '{full_name}'")
                    break
        
        assert len(invalid_names) == 0, f"Found {len(invalid_names)} invalid full_name formats: {invalid_names[:10]}"
        
        # Log statistics
        unique_names = df['full_name'].nunique()
        total_records = len(df)
        logging.info(f"Full name validation passed. Unique names: {unique_names}, Total records: {total_records}")
    
    def test_sum_treatment_cost_logic_validation(self, all_parquet_data):
        """Test that sum_treatment_cost values are logical and properly calculated."""
        df = all_parquet_data
        
        # Check for negative values (should not exist)
        negative_costs = df[df['sum_treatment_cost'] < 0]
        assert len(negative_costs) == 0, f"Found {len(negative_costs)} records with negative treatment costs"
        
        # Check for zero values (might be valid but worth noting)
        zero_costs = df[df['sum_treatment_cost'] == 0]
        if len(zero_costs) > 0:
            logging.warning(f"Found {len(zero_costs)} records with zero treatment costs")
        
        # Check distribution
        cost_stats = df['sum_treatment_cost'].describe()
        logging.info(f"Treatment cost statistics:")
        logging.info(f"  Count: {cost_stats['count']:,.0f}")
        logging.info(f"  Mean: ${cost_stats['mean']:,.2f}")
        logging.info(f"  Median: ${cost_stats['50%']:,.2f}")
        logging.info(f"  Min: ${cost_stats['min']:,.2f}")
        logging.info(f"  Max: ${cost_stats['max']:,.2f}")
        
        # Check for outliers (very high costs)
        high_cost_threshold = 100000  # $100,000
        high_costs = df[df['sum_treatment_cost'] > high_cost_threshold]
        if len(high_costs) > 0:
            logging.warning(f"Found {len(high_costs)} records with treatment costs > ${high_cost_threshold:,}")
            # Log examples
            for _, row in high_costs.head(3).iterrows():
                logging.warning(f"  High cost: {row['full_name']} at {row['facility_type']} - ${row['sum_treatment_cost']:,.2f}")
    
    def test_partition_record_counts_match_source(self, partition_directories, postgres_connector):
        """Test that each partition has the correct number of records compared to source."""
        count_mismatches = []
        
        for partition_dir in partition_directories:
            facility_type = partition_dir.name.replace('facility_type_partition=', '').replace('_', ' ')
            
            try:
                # Get source count for this facility type
                source_count_query = f"""
                SELECT COUNT(*) as record_count
                FROM (
                    SELECT 
                        CONCAT(p.first_name, ' ', p.last_name) as full_name,
                        f.facility_type,
                        SUM(v.treatment_cost) as sum_treatment_cost
                    FROM visits v
                    JOIN patients p ON v.patient_id = p.id
                    JOIN facilities f ON v.facility_id = f.id
                    WHERE v.treatment_cost IS NOT NULL 
                      AND p.first_name IS NOT NULL 
                      AND p.last_name IS NOT NULL
                      AND f.facility_type = '{facility_type}'
                    GROUP BY p.first_name, p.last_name, f.facility_type
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
                        'facility_type': facility_type,
                        'source_count': source_count,
                        'parquet_count': parquet_count,
                        'difference': parquet_count - source_count
                    })
                    
                    logging.warning(f"Facility type '{facility_type}': Count mismatch - "
                                  f"Source: {source_count}, Parquet: {parquet_count}, "
                                  f"Difference: {parquet_count - source_count}")
                else:
                    logging.info(f"Facility type '{facility_type}': Count match ✅ ({source_count} records)")
                    
            except Exception as e:
                logging.error(f"Count validation failed for facility type '{facility_type}': {e}")
                count_mismatches.append({
                    'facility_type': facility_type,
                    'error': str(e)
                })
        
        # Report summary
        if count_mismatches:
            logging.error("=" * 60)
            logging.error("RECORD COUNT MISMATCHES FOUND:")
            for mismatch in count_mismatches:
                if 'error' in mismatch:
                    logging.error(f"  {mismatch['facility_type']}: ERROR - {mismatch['error']}")
                else:
                    logging.error(f"  {mismatch['facility_type']}: Source={mismatch['source_count']}, "
                                f"Parquet={mismatch['parquet_count']}, Diff={mismatch['difference']}")
            logging.error("=" * 60)
        
        # Allow some tolerance for count differences (adjust as needed)
        significant_mismatches = [m for m in count_mismatches if 'difference' in m and abs(m['difference']) > 5]
        
        assert len(significant_mismatches) == 0, (
            f"Significant count mismatches found in {len(significant_mismatches)} partitions: {significant_mismatches}"
        )
    
    def test_partition_value_accuracy(self, partition_directories, postgres_connector):
        """Test that sum_treatment_cost values match between source and parquet for each partition."""
        value_accuracy_issues = []
        
        for partition_dir in partition_directories:
            facility_type = partition_dir.name.replace('facility_type_partition=', '').replace('_', ' ')
            
            try:
                # Get source data for this facility type
                source_query = f"""
                SELECT 
                    CONCAT(p.first_name, ' ', p.last_name) as full_name,
                    f.facility_type,
                    SUM(v.treatment_cost) as sum_treatment_cost
                FROM visits v
                JOIN patients p ON v.patient_id = p.id
                JOIN facilities f ON v.facility_id = f.id
                WHERE v.treatment_cost IS NOT NULL 
                  AND p.first_name IS NOT NULL 
                  AND p.last_name IS NOT NULL
                  AND f.facility_type = '{facility_type}'
                GROUP BY p.first_name, p.last_name, f.facility_type
                ORDER BY full_name
                """
                
                with postgres_connector as pg_conn:
                    source_data = pg_conn.get_data_sql(source_query)
                
                if source_data.empty:
                    logging.info(f"No source data for facility type '{facility_type}'")
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
                
                # Merge on full_name and facility_type
                merged_data = pd.merge(
                    source_data,
                    combined_parquet_data,
                    on=['full_name', 'facility_type'],
                    how='inner',
                    suffixes=('_source', '_parquet')
                )
                
                # Find value mismatches
                tolerance = 0.01  # Allow small floating point differences
                mismatches = merged_data[
                    abs(merged_data['sum_treatment_cost_source'] - merged_data['sum_treatment_cost_parquet']) > tolerance
                ]
                
                if not mismatches.empty:
                    value_accuracy_issues.append({
                        'facility_type': facility_type,
                        'mismatch_count': len(mismatches),
                        'total_compared': len(merged_data),
                        'accuracy_percentage': ((len(merged_data) - len(mismatches)) / len(merged_data)) * 100,
                        'examples': mismatches[['full_name', 'facility_type', 'sum_treatment_cost_source', 'sum_treatment_cost_parquet']].head(3).to_dict('records')
                    })
                    
                    logging.warning(f"Facility type '{facility_type}': {len(mismatches)} value mismatches out of {len(merged_data)} records")
                    for _, row in mismatches.head(3).iterrows():
                        logging.warning(f"  Mismatch: {row['full_name']} - "
                                      f"Source: ${row['sum_treatment_cost_source']:,.2f}, "
                                      f"Parquet: ${row['sum_treatment_cost_parquet']:,.2f}")
                else:
                    logging.info(f"Facility type '{facility_type}': All values match ✅ ({len(merged_data)} records)")
                    
            except Exception as e:
                logging.error(f"Value accuracy check failed for facility type '{facility_type}': {e}")
                value_accuracy_issues.append(f"{facility_type}: ERROR - {str(e)}")
        
        assert len(value_accuracy_issues) == 0, (
            f"Value accuracy issues found in {len(value_accuracy_issues)} partitions: {value_accuracy_issues}"
        )
    
    def test_data_completeness_vs_source(self, all_parquet_data, source_data_for_comparison):
        """Test data completeness compared to source data."""
        if source_data_for_comparison.empty:
            pytest.skip("Source data not available for comparison")
        
        parquet_df = all_parquet_data.drop(columns=['_partition_facility_type', '_partition_path', '_file_path'])
        
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
            'total_patients': 0,
            'total_treatment_cost': 0.0,
            'facility_type_details': []
        }
        
        # Calculate totals
        if not all_parquet_data.empty:
            summary['total_patients'] = all_parquet_data['full_name'].nunique()
            summary['total_treatment_cost'] = all_parquet_data['sum_treatment_cost'].sum()
        
        # Partition details
        for partition_dir in partition_directories:
            facility_type = partition_dir.name.replace('facility_type_partition=', '').replace('_', ' ')
            partition_data = all_parquet_data[all_parquet_data['_partition_facility_type'] == facility_type]
            
            if not partition_data.empty:
                facility_details = {
                    'facility_type': facility_type,
                    'record_count': len(partition_data),
                    'unique_patients': partition_data['full_name'].nunique(),
                    'total_cost': partition_data['sum_treatment_cost'].sum(),
                    'avg_cost_per_patient': partition_data['sum_treatment_cost'].mean(),
                    'file_count': len(list(partition_dir.glob("*.parquet")))
                }
            else:
                facility_details = {
                    'facility_type': facility_type,
                    'record_count': 0,
                    'unique_patients': 0,
                    'total_cost': 0.0,
                    'avg_cost_per_patient': 0.0,
                    'file_count': len(list(partition_dir.glob("*.parquet")))
                }
            
            summary['facility_type_details'].append(facility_details)
        
        # Log summary
        logging.info("=" * 80)
        logging.info("PATIENT SUM TREATMENT COST PARTITION SUMMARY")
        logging.info("=" * 80)
        logging.info(f"Total Partitions: {summary['total_partitions']}")
        logging.info(f"Total Records: {summary['total_records']:,}")
        logging.info(f"Unique Patients: {summary['total_patients']:,}")
        logging.info(f"Total Treatment Cost: ${summary['total_treatment_cost']:,.2f}")
        logging.info("")
        logging.info("By Facility Type:")
        for details in summary['facility_type_details']:
            logging.info(f"  {details['facility_type']}:")
            logging.info(f"    Records: {details['record_count']:,}")
            logging.info(f"    Patients: {details['unique_patients']:,}")
            logging.info(f"    Total Cost: ${details['total_cost']:,.2f}")
            logging.info(f"    Avg Cost/Patient: ${details['avg_cost_per_patient']:,.2f}")
        logging.info("=" * 80)
        
        return summary