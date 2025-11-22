import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from pathlib import Path
from typing import Optional, List, Dict, Any, Union
import logging
import os

class ParquetReader:
    """
    ParquetReader class for reading and processing Parquet files from the file system.
    Provides functionality for data quality validation and testing.
    """
    
    def __init__(self, base_path: Optional[str] = None):
        self.base_path = Path(base_path) if base_path else Path.cwd()
        self.logger = logging.getLogger(__name__)
        
        if not self.base_path.exists():
            raise FileNotFoundError(f"Base path does not exist: {self.base_path}")
    
    def read_parquet(self, file_path: Union[str, Path], 
                    columns: Optional[List[str]] = None,
                    filters: Optional[List[tuple]] = None) -> pd.DataFrame:
        """
        Read a Parquet file and return as pandas DataFrame.
        
        Args:
            file_path (Union[str, Path]): Path to the Parquet file (relative to base_path or absolute)
            columns (List[str], optional): Specific columns to read
            filters (List[tuple], optional): Filters to apply when reading
            
        Returns:
            pd.DataFrame: Data from the Parquet file
            
        Raises:
            FileNotFoundError: If the Parquet file doesn't exist
            Exception: If reading the file fails
        """
        # Resolve file path
        if isinstance(file_path, str):
            file_path = Path(file_path)
        
        # Make path absolute if it's relative
        if not file_path.is_absolute():
            file_path = self.base_path / file_path
        
        # Check if file exists
        if not file_path.exists():
            raise FileNotFoundError(f"Parquet file not found: {file_path}")
        
        try:
            self.logger.debug(f"Reading Parquet file: {file_path}")
            
            # Read Parquet file with optional parameters
            df = pd.read_parquet(
                file_path,
                columns=columns,
                filters=filters,
                engine='pyarrow'
            )
            
            self.logger.info(f"Successfully read Parquet file: {file_path}. "
                           f"Shape: {df.shape}")
            return df
            
        except Exception as e:
            self.logger.error(f"Failed to read Parquet file {file_path}: {e}")
            raise Exception(f"Error reading Parquet file: {e}")
    
    def get_parquet_metadata(self, file_path: Union[str, Path]) -> Dict[str, Any]:
        """
        Get metadata information from a Parquet file.
        
        Args:
            file_path (Union[str, Path]): Path to the Parquet file
            
        Returns:
            Dict[str, Any]: Metadata information including schema, row count, etc.
        """
        # Resolve file path
        if isinstance(file_path, str):
            file_path = Path(file_path)
        
        if not file_path.is_absolute():
            file_path = self.base_path / file_path
        
        if not file_path.exists():
            raise FileNotFoundError(f"Parquet file not found: {file_path}")
        
        try:
            # Read metadata using PyArrow
            parquet_file = pq.ParquetFile(file_path)
            metadata = parquet_file.metadata
            schema = parquet_file.schema
            
            metadata_info = {
                'file_path': str(file_path),
                'file_size_bytes': file_path.stat().st_size,
                'num_rows': metadata.num_rows,
                'num_columns': len(schema),
                'num_row_groups': metadata.num_row_groups,
                'schema': {
                    'columns': [field.name for field in schema],
                    'types': [str(field.type) for field in schema]
                },
                'created_by': metadata.created_by,
                'format_version': metadata.format_version
            }
            
            self.logger.debug(f"Retrieved metadata for: {file_path}")
            return metadata_info
            
        except Exception as e:
            self.logger.error(f"Failed to get metadata for {file_path}: {e}")
            raise Exception(f"Error getting Parquet metadata: {e}")
    
    def list_parquet_files(self, directory: Optional[Union[str, Path]] = None,
                          recursive: bool = True) -> List[Path]:
        """
        List all Parquet files in a directory.
        
        Args:
            directory (Union[str,
 Path], optional): Directory to search (defaults to base_path)
            recursive (bool): Whether to search recursively in subdirectories
            
        Returns:
            List[Path]: List of Parquet file paths
        """
        search_dir = Path(directory) if directory else self.base_path
        
        if not search_dir.is_absolute():
            search_dir = self.base_path / search_dir
        
        if not search_dir.exists():
            raise FileNotFoundError(f"Directory not found: {search_dir}")
        
        try:
            if recursive:
                parquet_files = list(search_dir.rglob("*.parquet"))
            else:
                parquet_files = list(search_dir.glob("*.parquet"))
            
            self.logger.info(f"Found {len(parquet_files)} Parquet files in {search_dir}")
            return sorted(parquet_files)
            
        except Exception as e:
            self.logger.error(f"Error listing Parquet files in {search_dir}: {e}")
            raise Exception(f"Error listing Parquet files: {e}")
    
    def validate_parquet_schema(self, file_path: Union[str, Path], 
                               expected_columns: List[str],
                               expected_types: Optional[Dict[str, str]] = None) -> bool:
        """
        Validate Parquet file schema against expected columns and types.
        
        Args:
            file_path (Union[str, Path]): Path to the Parquet file
            expected_columns (List[str]): Expected column names
            expected_types (Dict[str, str], optional): Expected column types
            
        Returns:
            bool: True if schema matches expectations, False otherwise
        """
        try:
            metadata = self.get_parquet_metadata(file_path)
            actual_columns = metadata['schema']['columns']
            actual_types = dict(zip(metadata['schema']['columns'], 
                                  metadata['schema']['types']))
            
            # Check columns
            if set(actual_columns) != set(expected_columns):
                missing_cols = set(expected_columns) - set(actual_columns)
                extra_cols = set(actual_columns) - set(expected_columns)
                
                if missing_cols:
                    self.logger.error(f"Missing columns: {missing_cols}")
                if extra_cols:
                    self.logger.error(f"Unexpected columns: {extra_cols}")
                return False
            
            # Check types if provided
            if expected_types:
                for col, expected_type in expected_types.items():
                    if col in actual_types:
                        if expected_type not in actual_types[col]:
                            self.logger.error(f"Column '{col}' type mismatch. "
                                            f"Expected: {expected_type}, "
                                            f"Actual: {actual_types[col]}")
                            return False
            
            self.logger.info(f"Schema validation passed for: {file_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Schema validation failed for {file_path}: {e}")
            return False
    
    def compare_with_dataframe(self, file_path: Union[str, Path], 
                              reference_df: pd.DataFrame,
                              compare_columns: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Compare Parquet file data with a reference DataFrame.
        
        Args:
            file_path (Union[str, Path]): Path to the Parquet file
            reference_df (pd.DataFrame): Reference DataFrame to compare against
            compare_columns (List[str], optional): Specific columns to compare
            
        Returns:
            Dict[str, Any]: Comparison results
        """
        try:
            # Read Parquet file
            parquet_df = self.read_parquet(file_path, columns=compare_columns)
            
            # Select columns for comparison
            if compare_columns:
                reference_df = reference_df[compare_columns]
                parquet_df = parquet_df[compare_columns]
            
            comparison_results = {
                'file_path': str(file_path),
                'rows_match': len(parquet_df) == len(reference_df),
                'parquet_rows': len(parquet_df),
                'reference_rows': len(reference_df),
                'columns_match': list(parquet_df.columns) == list(reference_df.columns),
                'parquet_columns': list(parquet_df.columns),
                'reference_columns': list(reference_df.columns),
                'data_identical': False
            }
            
            # Check if data is identical (if shapes match)
            if (comparison_results['rows_match'] and 
                comparison_results['columns_match']):
                try:
                    # Sort both DataFrames for comparison
                    parquet_sorted = parquet_df.sort_values(by=parquet_df.columns.tolist()).reset_index(drop=True)
                    reference_sorted = reference_df.sort_values(by=reference_df.columns.tolist()).reset_index(drop=True)
                    
                    comparison_results['data_identical'] = parquet_sorted.equals(reference_sorted)
                except Exception as e:
                    self.logger.warning(f"Could not compare data content: {e}")
                    comparison_results['data_identical'] = None
            
            self.logger.info(f"Comparison completed for: {file_path}")
            return comparison_results
            
        except Exception as e:
            self.logger.error(f"Comparison failed for {file_path}: {e}")
            raise Exception(f"Error comparing Parquet file with DataFrame: {e}")
    
    def get_file_info(self, file_path: Union[str, Path]) -> Dict[str, Any]:
        """
        Get comprehensive file information including metadata and basic statistics.
        
        Args:
            file_path (Union[str, Path]): Path to the Parquet file
            
        Returns:
            Dict[str, Any]: Comprehensive file information
        """
        try:
            # Get metadata
            metadata = self.get_parquet_metadata(file_path)
            
            # Read data for basic statistics
            df = self.read_parquet(file_path)
            
            # Calculate basic statistics
            file_info = {
                **metadata,
                'data_statistics': {
                    'memory_usage_mb': df.memory_usage(deep=True).sum() / (1024 * 1024),
                    'null_counts': df.isnull().sum().to_dict(),
                    'duplicate_rows': df.duplicated().sum(),
                    'numeric_columns': df.select_dtypes(include=['number']).columns.tolist(),
                    'string_columns': df.select_dtypes(include=['object', 'string']).columns.tolist(),
                    'datetime_columns': df.select_dtypes(include=['datetime']).columns.tolist()
                }
            }
            
            return file_info
            
        except Exception as e:
            self.logger.error(f"Failed to get file info for {file_path}: {e}")
            raise Exception(f"Error getting file information: {e}")