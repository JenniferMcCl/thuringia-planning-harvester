from sqlalchemy.dialects.postgresql import dialect
from sqlalchemy.schema import CreateTable

from thuringia_harvester.config import PROJECT_ROOT
from thuringia_harvester.models import SignalIngest


def test_initialization_sql_matches_model():
    ddl = str(
        CreateTable(SignalIngest.__table__, if_not_exists=True).compile(
            dialect=dialect()
        )
    )
    sql = (PROJECT_ROOT / "sql/init.sql").read_text()
    assert " ".join(ddl.split()) in " ".join(sql.split())
