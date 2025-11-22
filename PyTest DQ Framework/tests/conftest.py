import pytest
import os
import logging
from pathlib import Path
from typing import Optional, Dict, Any
import psycopg2
import pandas as pd

from postgres_connector import PostgresConnectorContextManager
from parquet_reader import ParquetReader

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def pytest_addoption(parser):
    """
    Add custom command line options for the test suite.
    These options allow configuration of database connections and file paths.
    """
    # Database connection options
    parser.addoption(
        "--db_host",
        action="store",
        default="localhost",
        help="PostgreSQL database host (default: localhost)"
    )
    
    parser.addoption(
        "--db_port",
        action="store",
        default="5432",
        type=int,
        help="PostgreSQL database port (default: 5432)"
    )
    
    parser.addoption(
        "--db_name",
        action="store",
        default="mydatabase",
        help="PostgreSQL database name (default: mydatabase)"
    )
    
    parser.addoption(
        "--db_user",
        action="store",
        default="myuser",
        help="PostgreSQL database user (default: myuser)"
    )
    # mypassword
    parser.addoption(
        "--db_schema",
        action="store",
        default="public",
        help="PostgreSQL database schema (default: public)"
    )
    
    # File path options
    parser.addoption(
        "--parquet-base-path",
        action="store",
        default=None,
        help="Base path for Parquet files (default: ./test_data/parquet)"
    )
    
    parser.addoption(
        "--test-data-path",
        action="store",
        default=None,
        help="Base path for test data files (default: ./test_data)"
    )
    
    # Test execution options
    parser.addoption(
        "--skip-db-tests",
        action="store_true",
        default=False,
        help="Skip database-dependent tests"
    )
    
    parser.addoption(
        "--generate-html-report",
        action="store_true",
        default=False,
        help="Generate HTML test report"
    )

def pytest_configure(config):
    """
    Configure pytest with custom markers and settings.
    """
    # Register custom markers
    config.addinivalue_line(
        "markers", 
        "parquet_data: mark test as parquet data validation test"
    )
    config.addinivalue_line(
        "markers", 
        "postgres_data: mark test as postgres data validation test"
    )
    config.addinivalue_line(
        "markers", 
        "data_transformation: mark test as data transformation validation test"
    )
    config.addinivalue_line(
        "markers", 
        "slow: mark test as slow running test"
    )
    config.addinivalue_line(
        "markers", 
        "integration: mark test as integration test"
    )

def pytest_collection_modifyitems(config, items):
    """
    Modify test collection based on command line options.
    """
    if config.getoption("--skip-db-tests"):
        skip_db = pytest.mark.skip(reason="Database tests skipped via --skip-db-tests")
        for item in items:
            if "postgres_data" in item.keywords:
                item.add_marker(skip_db)

@pytest.fixture(scope="session")
def db_config(request):
    """
    Session-scoped fixture that provides database configuration.
    
    Returns:
        Dict[str, Any]: Database connection configuration
    """
    # Get database password from environment variable for security
    db_password = os.getenv("POSTGRES_SECRET") or os.getenv("DB_PASSWORD", "password")
    
    config = {
        "db_host": request.config.getoption("--db_host"),
        "db_port": request.config.getoption("--db_port"),
        "db_name": request.config.getoption("--db_name"),
        "db_user": request.config.getoption("--db_user"),
        "db_password": db_password,
        "db_schema": request.config.getoption("--db_schema")
    }
    
    return config

@pytest.fixture(scope="function")
def postgres_connector(db_config):
    """
    Function-scoped fixture that provides PostgreSQL connector instance.
    
    Args:
        db_config: Database configuration from db_config fixture
        
    Returns:
        PostgresConnectorContextManager: Database connector instance

    """
    return PostgresConnectorContextManager(**db_config)

@pytest.fixture(scope="session")
def parquet_base_path(request):
    """
    Session-scoped fixture that provides the base path for Parquet files.
    
    Returns:
        Path: Base path for Parquet files
    """
    base_path = request.config.getoption("--parquet-base-path")
    
    if not base_path:
        # Default to test_data/parquet directory
        base_path = Path(__file__).parent / "test_data" / "parquet"
    else:
        base_path = Path(base_path)
    
    # Create directory if it doesn't exist
    base_path.mkdir(parents=True, exist_ok=True)
    
    return base_path

@pytest.fixture(scope="function")
def parquet_reader(parquet_base_path):
    """
    Function-scoped fixture that provides ParquetReader instance.
    
    Args:
        parquet_base_path: Base path for Parquet files
        
    Returns:
        ParquetReader: Parquet file reader instance
    """
    return ParquetReader(base_path=str(parquet_base_path))

@pytest.fixture(scope="session")
def test_data_path(request):
    """
    Session-scoped fixture that provides the base path for test data.
    
    Returns:
        Path: Base path for test data files
    """
    test_path = request.config.getoption("--test-data-path")
    
    if not test_path:
        test_path = Path(__file__).parent / "test_data"
    else:
        test_path = Path(test_path)
    
    # Create directory if it doesn't exist
    test_path.mkdir(parents=True, exist_ok=True)
    
    return test_path

@pytest.fixture(scope="function")
def sample_postgres_data(postgres_connector):
    """
    Fixture that provides sample data from PostgreSQL for testing.
    
    Args:
        postgres_connector: PostgreSQL connector instance
        
    Returns:
        pd.DataFrame: Sample data from database
    """
    sample_query = """
    SELECT 
        id,
        name,
        created_date,
        status,
        amount
    FROM sample_table 
    LIMIT 100
    """
    
    with postgres_connector as pg_conn:
        return pg_conn.get_data_sql(sample_query)

@pytest.fixture(scope="function")
def data_quality_thresholds():
    """
    Fixture that provides data quality validation thresholds.
    
    Returns:
        Dict[str, Any]: Data quality thresholds and limits
    """
    return {
        "max_null_percentage": 5.0,  # Maximum 5% null values allowed
        "min_row_count": 1,          # Minimum 1 row required
        "max_duplicate_percentage": 2.0,  # Maximum 2% duplicates allowed
        "required_columns": ["id", "name", "created_date"],
        "numeric_columns_min_max": {
            "amount": {"min": 0, "max": 1000000}
        },
        "string_columns_max_length": {
            "name": 255,
            "status": 50
        }
    }

@pytest.fixture(autouse=True)
def setup_test_logging(caplog):
    """
    Auto-use fixture that sets up logging for each test.
    
    Args:
        caplog: pytest's log capture fixture
    """
    caplog.set_level(logging.INFO)

def pytest_runtest_setup(item):
    """
    Hook that runs before each test to perform setup.
    """
    # Log test start
    logging.info(f"Starting test: {item.name}")

def pytest_runtest_teardown(item, nextitem):
    """
    Hook that runs after each test to perform cleanup.
    """
    # Log test completion
    logging.info(f"Completed test: {item.name}")

def pytest_sessionstart(session):
    """
    Hook that runs at the start of the test session.
    """
    logging.info("=" * 60)
    logging.info("Starting Data Quality Test Suite")
    logging.info("=" * 60)

def pytest_sessionfinish(session, exitstatus):
    """
    Hook that runs at the end of the test session.
    """
    logging.info("=" * 60)
    logging.info(f"Data Quality Test Suite completed with exit status: {exitstatus}")
    logging.info("=" * 60)

# Error handling fixtures
@pytest.fixture
def handle_db_connection_error():
    """
    Fixture to handle database connection errors gracefully.
    """
    def _handle_error(func, *args, **kwargs):
        try:
            return func(*args, **kwargs)
        except psycopg2.OperationalError as e:
            pytest.skip(f"Database connection failed: {e}")
        except Exception as e:
            pytest.fail(f"Unexpected error: {e}")
    
    return _handle_error