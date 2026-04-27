# Author: ZOYA KHAN
# Date: 2026-04-26
# Team Member: HANIA
# Date: 2026-04-26
# Description: Merged config — database host, timeout, and health check settings

import os

MYSQL_HOST = os.environ.get('MYSQL_HOST', 'sakila-db-server')
MYSQL_USER = os.environ.get('MYSQL_USER', 'root')
MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD', '')
MYSQL_DB = os.environ.get('MYSQL_DB', 'sakila')
# CONNECTION_TIMEOUT: seconds before DB connection attempt times out (consider 10s for faster failure detection)
CONNECTION_TIMEOUT = int(os.environ.get('CONNECTION_TIMEOUT', '30'))
HEALTH_CHECK_INTERVAL = int(os.environ.get('HEALTH_CHECK_INTERVAL', '10'))