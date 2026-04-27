# Team Member: HANIA
# Date: 2026-04-26
# Description: Added health check interval

import os

MYSQL_HOST = os.environ.get('MYSQL_HOST', 'db-primary')
MYSQL_USER = os.environ.get('MYSQL_USER', 'root')
MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD', '')
MYSQL_DB = os.environ.get('MYSQL_DB', 'sakila')
HEALTH_CHECK_INTERVAL = int(os.environ.get('HEALTH_CHECK_INTERVAL', '10'))