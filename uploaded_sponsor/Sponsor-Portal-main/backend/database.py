"""Shared database connection module with connection pooling"""
from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection with connection pooling configuration
mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
db_name = os.environ.get('DB_NAME', 'bighat_trivia')

# Connection pool settings for high traffic
# maxPoolSize: Maximum number of connections in the pool
# minPoolSize: Minimum number of connections to maintain
# maxIdleTimeMS: How long a connection can be idle before being closed
# connectTimeoutMS: How long to wait for a connection
# serverSelectionTimeoutMS: How long to wait for server selection
client = AsyncIOMotorClient(
    mongo_url,
    maxPoolSize=50,           # Max 50 concurrent connections
    minPoolSize=10,           # Keep at least 10 connections ready
    maxIdleTimeMS=30000,      # Close idle connections after 30 seconds
    connectTimeoutMS=5000,    # 5 second connection timeout
    serverSelectionTimeoutMS=5000,  # 5 second server selection timeout
    retryWrites=True,         # Automatically retry failed writes
    retryReads=True,          # Automatically retry failed reads
)
db = client[db_name]
