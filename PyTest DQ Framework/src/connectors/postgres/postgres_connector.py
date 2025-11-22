import psycopg2
import pandas as pd
from typing import Optional, Any
import logging

class PostgresConnectorContextManager:
    """
    PostgreSQL connector with context manager support for data quality testing.
    Handles database connections and executes SQL queries returning pandas DataFrames.
    """
    
    def __init__(self, db_host: str, db_name: str, db_user: str, db_password: str, 
                 db_port: int = 5432, db_schema: str = 'public'):
        """
        Initialize PostgreSQL connector with database connection parameters.
        
        Args:
            db_host (str): Database host address
            db_name (str): Database name
            db_user (str): Database username
            db_password (str): Database password
            db_port (int): Database port (default: 5432)
            db_schema (str): Database schema (default: 'public')
        """
        self.db_host = db_host
        self.db_name = db_name
        self.db_user = db_user
        self.db_password = db_password
        self.db_port = db_port
        self.db_schema = db_schema
        self.connection: Optional[psycopg2.extensions.connection] = None
        self.cursor: Optional[psycopg2.extensions.cursor] = None
        
        # Set up logging
        self.logger = logging.getLogger(__name__)
    
    def __enter__(self):
        """
        Enter context manager - establish database connection.
        
        Returns:
            PostgresConnectorContextManager: Self instance
        """
        try:
            # Create database connection
            self.connection = psycopg2.connect(
                host=self.db_host,
                database=self.db_name,
                user=self.db_user,
                password=self.db_password,
                port=self.db_port
            )
            
            # Create cursor
            self.cursor = self.connection.cursor()
            
            # Set search path to specified schema
            if self.db_schema != 'public':
                self.cursor.execute(f"SET search_path TO {self.db_schema}")
                self.connection.commit()
            
            self.logger.info(f"Successfully connected to PostgreSQL database: {self.db_name}")
            return self
            
        except psycopg2.Error as e:
            self.logger.error(f"Failed to connect to PostgreSQL database: {e}")
            raise ConnectionError(f"Database connection failed: {e}")
    
    def __exit__(self, exc_type: Optional[type], exc_value: Optional[Exception], 
                 exc_tb: Optional[Any]) -> None:
        """
        Exit context manager - close database connection and cursor.
        
        Args:
            exc_type: Exception type if an exception occurred
            exc_value: Exception value if an exception occurred
            exc_tb: Exception traceback if an exception occurred
        """
        try:
            # Close cursor if it exists
            if self.cursor:
                self.cursor.close()
                self.logger.debug("Database cursor closed")
            
            # Close connection if it exists
            if self.connection:
                self.connection.close()
                self.logger.info("Database connection closed")
                
        except psycopg2.Error as e:
            self.logger.error(f"Error closing database connection: {e}")
        
        finally:
            self.cursor = None
            self.connection = None
    
    def get_data_sql(self, sql: str) -> pd.DataFrame:
        """
        Execute SQL query and return results as pandas DataFrame.
        
        Args:
            sql (str): SQL query to execute
            
        Returns:
            pd.DataFrame: Query results as pandas DataFrame
            
        Raises:
            RuntimeError: If connection is not established
            psycopg2.Error: If SQL execution fails
        """
        if not self.connection or not self.cursor:
            raise RuntimeError("Database connection not established. Use within context manager.")
        
        try:
            self.logger.debug(f"Executing SQL query: {sql[:100]}...")
            
            # Execute query and fetch results using pandas
            df = pd.read_sql_query(sql, self.connection)
            
            self.logger.info(f"Query executed successfully. Retrieved {len(df)} rows, {len(df.columns)} columns")
            return df
            
        except psycopg2.Error as e:
            self.logger.error(f"SQL execution failed: {e}")
            raise psycopg2.Error(f"Failed to execute SQL query: {e}")
        
        except Exception as e:
            self.logger.error(f"Unexpected error during SQL execution: {e}")
            raise RuntimeError(f"Unexpected error: {e}")
    
    def test_connection(self) -> bool:
        """
        Test database connection without executing queries.
        
        Returns:
            bool: True if connection is successful, False otherwise
        """
        if not self.connection:
            return False
        
        try:
            # Test connection with simple query
            self.cursor.execute("SELECT 1")
            result = self.cursor.fetchone()
            return result[0] == 1
            
        except psycopg2.Error:
            return False