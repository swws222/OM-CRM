#!/bin/sh
set -eu
cd /workspace/OM-CRM
python3 -c 'import sys; assert sys.version_info >= (3,11), "Python 3.11+ required"'
# Runtime uses only the standard library. Do not regenerate source data or reset an existing database.
python3 -c 'import server; server.init()'
