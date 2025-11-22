import pandas as pd
import numpy as np
from typing import List, Optional, Union, Dict, Any
import logging

class DataQualityLibrary:
    """
    A library of static methods for performing data quality checks on pandas DataFrames.

    This class is intended to be used in a PyTest-based testing framework to validate
    the quality of data in DataFrames. Each method performs a specific data quality
    check and uses assertions to ensure that the data meets the expected conditions.
    """

    @staticmethod
    def check_duplicates(df: pd.DataFrame, column_names: Optional[List[str]] = None, 
                        max_duplicates: int = 0) -> Dict[str, Any]:
        """
        Check for duplicate rows in the DataFrame.
        
        Args:
            df (pd.DataFrame): DataFrame to check for duplicates
            column_names (List[str], optional): Specific columns to check for duplicates.
                                              If None, checks all columns.
            max_duplicates (int): Maximum number of duplicates allowed (default: 0)
            
        Returns:
            Dict[str, Any]: Dictionary containing duplicate check results
            
        Raises:
            AssertionError: If duplicate count exceeds max_duplicates
        """
        if df.empty:
            return {
                'duplicate_count': 0,
                'duplicate_percentage': 0.0,
                'has_duplicates': False,
                'duplicate_rows': pd.DataFrame()
            }
        
        if column_names:
            # Check duplicates based on specific columns
            duplicates_mask = df.duplicated(subset=column_names, keep=False)
            duplicate_rows = df[duplicates_mask]
            duplicate_count = df.duplicated(subset=column_names).sum()
        else:
            # Check duplicates across all columns
            duplicates_mask = df.duplicated(keep=False)
            duplicate_rows = df[duplicates_mask]
            duplicate_count = df.duplicated().sum()
        
        duplicate_percentage = (duplicate_count / len(df)) * 100 if len(df) > 0 else 0.0
        
        result = {
            'duplicate_count': duplicate_count,
            'duplicate_percentage': duplicate_percentage,
            'has_duplicates': duplicate_count > 0,
            'duplicate_rows': duplicate_rows,
            'columns_checked': column_names or list(df.columns)
        }
        
        # Assert that duplicates don't exceed the maximum allowed
        assert duplicate_count <= max_duplicates, (
            f"Duplicate check failed: Found {duplicate_count} duplicates, "
            f"maximum allowed: {max_duplicates}. "
            f"Duplicate percentage: {duplicate_percentage:.2f}%"
        )
        
        return result

    @staticmethod
    def check_count(df1: pd.DataFrame, df2: pd.DataFrame, 
                   tolerance: float = 0.0) -> Dict[str, Any]:
        """
        Compare row counts between two DataFrames.
        
        Args:
            df1 (pd.DataFrame): First DataFrame
            df2 (pd.DataFrame): Second DataFrame
            tolerance (float): Percentage tolerance for count difference (0-100)
            
        Returns:
            Dict[str, Any]: Dictionary containing count comparison results
            
        Raises:
            AssertionError: If count difference exceeds tolerance
        """
        count1 = len(df1)
        count2 = len(df2)
        count_diff = abs(count1 - count2)
        
        if count1 > 0:
            percentage_diff = (count_diff / count1) * 100
        else:
            percentage_diff = 100.0 if count2 > 0 else 0.0
        
        result = {
            'df1_count': count1,
            'df2_count': count2,
            'count_difference': count_diff,
            'percentage_difference': percentage_diff,
            'counts_match': count1 == count2
        }
        
        # Assert that count difference is within tolerance
        assert percentage_diff <= tolerance, (
            f"Count check failed: DataFrame counts differ by {count_diff} rows "
            f"({percentage_diff:.2f}%), tolerance: {tolerance}%. "
            f"DF1: {count1} rows, DF2: {count2} rows"
        )
        
        return result

    @staticmethod
    def check_data_full_data_set(df1: pd.DataFrame, df2: pd.DataFrame, 
                                key_columns: Optional[List[str]] = None,
                                compare_columns: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Compare two DataFrames for data completeness and equality.
        
        Args:
            df1 (pd.DataFrame): First DataFrame (source
)
            df2 (pd.DataFrame): Second DataFrame (target)
            key_columns (List[str], optional): Columns to use as keys for comparison
            compare_columns (List[str], optional): Specific columns to compare
            
        Returns:
            Dict[str, Any]: Dictionary containing data comparison results
            
        Raises:
            AssertionError: If DataFrames are not equivalent
        """
        # Select columns to compare
        if compare_columns:
            df1_compare = df1[compare_columns].copy()
            df2_compare = df2[compare_columns].copy()
        else:
            df1_compare = df1.copy()
            df2_compare = df2.copy()
        
        # Sort DataFrames for comparison if key columns are provided
        if key_columns:
            df1_compare = df1_compare.sort_values(by=key_columns).reset_index(drop=True)
            df2_compare = df2_compare.sort_values(by=key_columns).reset_index(drop=True)
        
        # Check shapes
        shapes_match = df1_compare.shape == df2_compare.shape
        
        # Check column names
        columns_match = list(df1_compare.columns) == list(df2_compare.columns)
        
        # Check data equality
        data_equal = False
        if shapes_match and columns_match:
            try:
                data_equal = df1_compare.equals(df2_compare)
            except Exception:
                # If direct comparison fails, try element-wise comparison
                data_equal = False
        
        result = {
            'shapes_match': shapes_match,
            'df1_shape': df1_compare.shape,
            'df2_shape': df2_compare.shape,
            'columns_match': columns_match,
            'df1_columns': list(df1_compare.columns),
            'df2_columns': list(df2_compare.columns),
            'data_equal': data_equal,
            'key_columns_used': key_columns,
            'compare_columns_used': compare_columns or list(df1.columns)
        }
        
        # Assert that DataFrames are equivalent
        assert shapes_match, (
            f"Shape mismatch: DF1 shape {df1_compare.shape}, "
            f"DF2 shape {df2_compare.shape}"
        )
        
        assert columns_match, (
            f"Column mismatch: DF1 columns {list(df1_compare.columns)}, "
            f"DF2 columns {list(df2_compare.columns)}"
        )
        
        assert data_equal, (
            "Data content mismatch: DataFrames have different values"
        )
        
        return result

    @staticmethod
    def check_dataset_is_not_empty(df: pd.DataFrame, 
                                  min_rows: int = 1) -> Dict[str, Any]:
        """
        Check that the DataFrame is not empty and meets minimum row requirements.
        
        Args:
            df (pd.DataFrame): DataFrame to check
            min_rows (int): Minimum number of rows required (default: 1)
            
        Returns:
            Dict[str, Any]: Dictionary containing emptiness check results
            
        Raises:
            AssertionError: If DataFrame is empty or doesn't meet minimum row requirement
        """
        row_count = len(df)
        col_count = len(df.columns) if not df.empty else 0
        is_empty = df.empty
        meets_min_rows = row_count >= min_rows
        
        result = {
            'is_empty': is_empty,
            'row_count': row_count,
            'column_count': col_count,
            'min_rows_required': min_rows,
            'meets_min_rows': meets_min_rows
        }
        
        # Assert that DataFrame is not empty
        assert not is_empty, "Dataset is empty: DataFrame contains no data"
        
        # Assert that DataFrame meets minimum row requirement
        assert meets_min_rows, (
            f"Dataset too small: Found {row_count} rows, "
            f"minimum required: {min_rows}"
        )
        
        return result

    @staticmethod
    def check_not_null_values(df: pd.DataFrame, 
                             column_names: Optional[List[str]] = None,
                             max_null_percentage: float = 0.0) -> Dict[str, Any]:
        """
        Check for null values in specified columns.
        
        Args:
            df (pd.DataFrame): DataFrame to check for null values
            column_names (List[str], optional): Specific columns to check.
                                              If None, checks all columns.
            max_null_percentage (float): Maximum percentage of null values allowed (0-100)
            
        Returns:
            Dict[str, Any]: Dictionary containing null value check results
            
        Raises:
            AssertionError: If null percentage exceeds max_null_percentage
        """
        if df.empty:
            return {
                'null_counts': {},
                'null_percentages': {},
                'total_nulls': 0,
                'columns_with_nulls': [],
                'columns_checked': column_names or []
            }
        
        # Determine columns to check
        columns_to_check = column_names if column_names else list(df.columns)
        
        # Validate that specified columns exist
        missing_columns = [col for col in columns_to_check if col not in df.columns]
        if missing_columns:
            raise ValueError(f"Columns not found in DataFrame: {missing_columns}")
        
        # Calculate null counts and percentages
        null_counts = {}
        null_percentages = {}
        columns_with_nulls = []
        
        for col in columns_to_check:
            null_count = df[col].isnull().sum()
            null_percentage = (null_count / len(df)) * 100 if len(df) > 0 else 0.0
            
            null_counts[col] = null_count
            null_percentages[col] = null_percentage
            
            if null_count > 0:
                columns_with_nulls.append(col)
        
        total_nulls = sum(null_counts.values())
        
        result = {
            'null_counts': null_counts,
            'null_percentages': null_percentages,
            'total_nulls': total_nulls,
            'columns_with_nulls': columns_with_nulls,
            'columns_checked': columns_to_check,
            'max_null_percentage_allowed': max_null_percentage
        }
        
        # Assert that null percentages don't exceed maximum allowed
        for col, percentage in null_percentages.items():
            assert percentage <= max_null_percentage, (
                f"Null value check failed for column '{col}': "
                f"Found {percentage:.2f}% null values, "
                f"maximum allowed: {max_null_percentage}%. "
                f"Null count: {null_counts[col]}/{len(df)}"
            )
        
        return result

    @staticmethod
    def check_column_exists(df: pd.DataFrame,column_names: List[str]) -> Dict[str, Any]:
        """
        Check that specified columns exist in the DataFrame.
        
        Args:
            df (pd.DataFrame): DataFrame to check
            column_names (List[str]): List of column names to verify
            
        Returns:
            Dict[str, Any]: Dictionary containing column existence check results
            
        Raises:
            AssertionError: If any required columns are missing
        """
        existing_columns = list(df.columns)
        missing_columns = [col for col in column_names if col not in existing_columns]
        present_columns = [col for col in column_names if col in existing_columns]
        
        result = {
            'required_columns': column_names,
            'existing_columns': existing_columns,
            'missing_columns': missing_columns,
            'present_columns': present_columns,
            'all_columns_present': len(missing_columns) == 0
        }
        
        # Assert that all required columns are present
        assert len(missing_columns) == 0, (
            f"Missing required columns: {missing_columns}. "
            f"Available columns: {existing_columns}"
        )
        
        return result

    @staticmethod
    def check_data_types(df: pd.DataFrame, 
                        expected_types: Dict[str, str]) -> Dict[str, Any]:
        """
        Check that columns have expected data types.
        
        Args:
            df (pd.DataFrame): DataFrame to check
            expected_types (Dict[str, str]): Dictionary mapping column names to expected types
            
        Returns:
            Dict[str, Any]: Dictionary containing data type check results
            
        Raises:
            AssertionError: If any columns have incorrect data types
        """
        actual_types = {col: str(df[col].dtype) for col in df.columns}
        type_mismatches = {}
        
        for col, expected_type in expected_types.items():
            if col not in df.columns:
                type_mismatches[col] = {
                    'expected': expected_type,
                    'actual': 'COLUMN_NOT_FOUND',
                    'match': False
                }
            else:
                actual_type = str(df[col].dtype)
                type_match = expected_type in actual_type or actual_type in expected_type
                
                if not type_match:
                    type_mismatches[col] = {
                        'expected': expected_type,
                        'actual': actual_type,
                        'match': False
                    }
        
        result = {
            'expected_types': expected_types,
            'actual_types': actual_types,
            'type_mismatches': type_mismatches,
            'all_types_correct': len(type_mismatches) == 0
        }
        
        # Assert that all data types are correct
        assert len(type_mismatches) == 0, (
            f"Data type mismatches found: {type_mismatches}"
        )
        
        return result

    @staticmethod
    def check_value_range(df: pd.DataFrame, 
                         column_name: str,
                         min_value: Optional[Union[int, float]] = None,
                         max_value: Optional[Union[int, float]] = None) -> Dict[str, Any]:
        """
        Check that values in a numeric column fall within specified range.
        
        Args:
            df (pd.DataFrame): DataFrame to check
            column_name (str): Name of the column to check
            min_value (Union[int, float], optional): Minimum allowed value
            max_value (Union[int, float], optional): Maximum allowed value
            
        Returns:
            Dict[str, Any]: Dictionary containing value range check results
            
        Raises:
            AssertionError: If values fall outside the specified range
        """
        if column_name not in df.columns:
            raise ValueError(f"Column '{column_name}' not found in DataFrame")
        
        column_data = df[column_name].dropna()  # Exclude null values
        
        if column_data.empty:
            return {
                'column_name': column_name,
                'min_value_constraint': min_value,
                'max_value_constraint': max_value,
                'actual_min': None,
                'actual_max': None,
                'values_in_range': True
,
                'out_of_range_count': 0
            }
        
        actual_min = column_data.min()
        actual_max = column_data.max()
        
        # Check range violations
        out_of_range_mask = pd.Series([False] * len(column_data))
        
        if min_value is not None:
            out_of_range_mask |= (column_data < min_value)
        
        if max_value is not None:
            out_of_range_mask |= (column_data > max_value)
        
        out_of_range_count = out_of_range_mask.sum()
        values_in_range = out_of_range_count == 0
        
        result = {
            'column_name': column_name,
            'min_value_constraint': min_value,
            'max_value_constraint': max_value,
            'actual_min': actual_min,
            'actual_max': actual_max,
            'values_in_range': values_in_range,
            'out_of_range_count': out_of_range_count,
            'total_non_null_values': len(column_data)
        }
        
        # Assert that all values are in range
        if min_value is not None:
            assert actual_min >= min_value, (
                f"Value range check failed for column '{column_name}': "
                f"Found minimum value {actual_min}, expected >= {min_value}"
            )
        
        if max_value is not None:
            assert actual_max <= max_value, (
                f"Value range check failed for column '{column_name}': "
                f"Found maximum value {actual_max}, expected <= {max_value}"
            )
        
        return result

    @staticmethod
    def check_uniqueness(df: pd.DataFrame, 
                        column_names: List[str],
                        allow_nulls: bool = True) -> Dict[str, Any]:
        """
        Check that specified columns contain unique values.
        
        Args:
            df (pd.DataFrame): DataFrame to check
            column_names (List[str]): List of columns that should contain unique values
            allow_nulls (bool): Whether to allow null values in uniqueness check
            
        Returns:
            Dict[str, Any]: Dictionary containing uniqueness check results
            
        Raises:
            AssertionError: If uniqueness constraint is violated
        """
        if not allow_nulls:
            # Check for nulls first if not allowed
            null_check = DataQualityLibrary.check_not_null_values(df, column_names, 0.0)
        
        # Check uniqueness for the combination of columns
        if len(column_names) == 1:
            # Single column uniqueness
            col = column_names[0]
            if allow_nulls:
                unique_count = df[col].nunique()
                total_count = len(df)
            else:
                non_null_data = df[col].dropna()
                unique_count = non_null_data.nunique()
                total_count = len(non_null_data)
        else:
            # Multi-column uniqueness
            if allow_nulls:
                unique_count = df[column_names].drop_duplicates().shape[0]
                total_count = len(df)
            else:
                non_null_data = df[column_names].dropna()
                unique_count = non_null_data.drop_duplicates().shape[0]
                total_count = len(non_null_data)
        
        is_unique = unique_count == total_count
        duplicate_count = total_count - unique_count
        
        result = {
            'columns_checked': column_names,
            'unique_count': unique_count,
            'total_count': total_count,
            'duplicate_count': duplicate_count,
            'is_unique': is_unique,
            'allow_nulls': allow_nulls
        }
        
        # Assert uniqueness
        assert is_unique, (
            f"Uniqueness check failed for columns {column_names}: "
            f"Found {duplicate_count} duplicate combinations out of {total_count} total rows"
        )
        
        return result