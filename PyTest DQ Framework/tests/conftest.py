import pytest
import os
import logging
from pathlib import Path
from typing import Optional, Dict, Any
import psycopg2
import pandas as pd

# Load environment variables from .env file
from dotenv import load_dotenv

# Load .env file from project root
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

# Add src to Python path
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

# Import your custom classes with correct paths
from connectors.postgres.postgres_connector import PostgresConnectorContextManager
from connectors.file_system.parquet_reader import ParquetReader
from data_quality.data_quality_validation_library import DataQualityLibrary

# Configure logging for tests
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def pytest_addoption(parser):
    """Add custom command line options for the test suite."""
    # Database connection options
    parser.addoption("--db_host", action="store", default="localhost", help="PostgreSQL database host")
    parser.addoption("--db_port", action="store", default="5434", type=int, help="PostgreSQL database port")
    parser.addoption("--db_name", action="store", default="mydatabase", help="PostgreSQL database name")
    parser.addoption("--db_user", action="store", default="myuser", help="PostgreSQL database user")
    parser.addoption("--db_password", action="store", default="mypassword", help="PostgreSQL database password")
    parser.addoption("--db_schema", action="store", default="public", help="PostgreSQL database schema")
    parser.addoption("--facility-name-min-time-path",action="store", default=None, help="Path to facility_name_min_time_spent_per_visit_date directory")
    parser.addoption("--facility-type-avg-time-path",action="store", default=None, help="Path to facility_type_avg_time_spent_per_visit_date directory")
    parser.addoption("--patient-sum-treatment-cost-path",action="store", default=None, help="Path to patient_sum_treatment_cost_per_facility_type directory")
    parser.addoption("--parquet-root-path", action="store",default="/parquet_data", help="Root path for all parquet data directories (default: /parquet_data)")
    parser.addoption("--skip-db-tests", action="store_true", default=False, help="Skip database-dependent tests")

def pytest_configure(config):
    """Configure pytest with custom markers and settings."""
    config.addinivalue_line("markers", "parquet_data: mark test as parquet data validation test")
    config.addinivalue_line("markers", "postgres_data: mark test as postgres data validation test")
    config.addinivalue_line("markers", "data_transformation: mark test as data transformation validation test")
    config.addinivalue_line("markers", "slow: mark test as slow running test")

@pytest.fixture(scope="session")
def db_config(request):
    """Session-scoped fixture that provides database configuration."""
    config = {
        "db_host": request.config.getoption("--db_host") or os.getenv("DB_HOST", "localhost"),
        "db_port": int(request.config.getoption("--db_port") or os.getenv("DB_PORT", "5432")),
        "db_name": request.config.getoption("--db_name") or os.getenv("DB_NAME", "mydatabase"),
        "db_user": request.config.getoption("--db_user") or os.getenv("DB_USER") or os.getenv("POSTGRES_SECRET_USR", "myuser"),
        "db_password": request.config.getoption("--db_password") or os.getenv("DB_PASSWORD") or os.getenv("POSTGRES_SECRET_PSW", "mypassword"),
        "db_schema": request.config.getoption("--db_schema") or os.getenv("DB_SCHEMA", "public")
    }
    return config

@pytest.fixture(scope="session")  # Changed from function to session
def postgres_connector(db_config):
    """
    Session-scoped fixture that provides PostgreSQL connector instance.
    """
    return PostgresConnectorContextManager(**db_config)

@pytest.fixture(scope="session")
def parquet_base_path(request):
    """Session-scoped fixture that provides the base path for Parquet files."""
    base_path = request.config.getoption("--parquet-base-path")
    
    if not base_path:
        base_path = Path(__file__).parent / "test_data" / "parquet"
    else:
        base_path = Path(base_path)
    
    base_path.mkdir(parents=True, exist_ok=True)
    return base_path

@pytest.fixture(scope="session")  # Changed from function to session
def parquet_reader(parquet_base_path):
    """
    Session-scoped fixture that provides ParquetReader instance.
    """
    return ParquetReader(base_path=str(parquet_base_path))

@pytest.fixture(scope="session")
def data_quality_library():
    """
    Session-scoped fixture that provides an instance of DataQualityLibrary.
    """
    return DataQualityLibrary()

@pytest.fixture(scope="session")
def test_data_path(request):
    """Session-scoped fixture that provides the base path for test data."""
    test_path = request.config.getoption("--test-data-path")
    
    if not test_path:
        test_path = Path(__file__).parent / "test_data"
    else:
        test_path = Path(test_path)
    
    test_path.mkdir(parents=True, exist_ok=True)
    return test_path

@pytest.fixture(scope="function")
def data_quality_thresholds():
    """Fixture that provides data quality validation thresholds."""
    return {
        "max_null_percentage": 5.0,
        "min_row_count": 1,
        "max_duplicate_percentage": 2.0,
        "required_columns": ["id", "name", "created_date"],
        "numeric_columns_min_max": {"amount": {"min": 0, "max": 1000000}},
        "string_columns_max_length": {"name": 255, "status": 50}
    }

def pytest_runtest_setup(item):
    """Hook that runs before each test to perform setup."""
    logging.info(f"Starting test: {item.name}")

def pytest_runtest_teardown(item, nextitem):
    """Hook that runs after each test to perform cleanup."""
    logging.info(f"Completed test: {item.name}")

def pytest_sessionstart(session):
    """Hook that runs at the start of the test session."""
    logging.info("=" * 60)
    logging.info("Starting Data Quality Test Suite")
    logging.info("=" * 60)

def pytest_sessionfinish(session, exitstatus):
    """Hook that runs at the end of the test session."""
    logging.info("=" * 60)
    logging.info(f"Data Quality Test Suite completed with exit status: {exitstatus}")
    logging.info("=" * 60)