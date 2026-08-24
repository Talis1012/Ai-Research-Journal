"""Presentation-only local identity shim.

Loaded through PYTHONPATH for the temporary screenshot server. The repository
authentication code remains unchanged.
"""

import os
import sqlite3
import time

import db.database as database
import db.data_analysis_queries as data_analysis_queries
import db.discovery_queries as discovery_queries
import db.library_queries as library_queries
import db.queries as project_queries
import db.research_case_queries as research_case_queries
import db.writing_queries as writing_queries
import services.resource_limits as resource_limits
import services.workspace_service as workspace_service
import utils.auth as auth
import utils.query_cache as query_cache
import utils.runtime_config as runtime_config
from utils.user_scope import activate_user_scope


PRESENTATION_CLAIMS = {
    "iss": "https://presentation.local/",
    "sub": "auth0|internship-presentation",
    "role": "authenticated",
    "name": "Vlad Ciripescu",
    "email": "vlad@example.local",
    "exp": time.time() + 86400,
}


def presentation_require_auth():
    activate_user_scope(
        PRESENTATION_CLAIMS["iss"],
        PRESENTATION_CLAIMS["sub"],
        claims=PRESENTATION_CLAIMS,
    )
    return dict(PRESENTATION_CLAIMS)


def presentation_user_profile():
    return {
        "name": PRESENTATION_CLAIMS["name"],
        "email": PRESENTATION_CLAIMS["email"],
        "picture": "",
    }


auth.require_auth = presentation_require_auth
auth.current_user_profile = presentation_user_profile
auth.logout = lambda: None


def presentation_db_path():
    """Use the exact temporary database selected for screenshot generation."""
    return os.environ["DATABASE_PATH"]


database.get_db_path = presentation_db_path


def presentation_connection():
    connection = sqlite3.connect(presentation_db_path())
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


database.get_connection = presentation_connection
database._get_sqlite_connection = presentation_connection
runtime_config.uses_postgres = lambda: False
database.uses_postgres = runtime_config.uses_postgres
library_queries.uses_postgres = runtime_config.uses_postgres
research_case_queries.uses_postgres = runtime_config.uses_postgres
resource_limits.uses_postgres = runtime_config.uses_postgres
workspace_service.uses_postgres = runtime_config.uses_postgres
query_cache.uses_postgres = runtime_config.uses_postgres
for query_module in (
    project_queries,
    library_queries,
    discovery_queries,
    writing_queries,
    data_analysis_queries,
    research_case_queries,
):
    query_module.get_connection = presentation_connection
