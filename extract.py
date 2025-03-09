from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker

from table_definitions import DatabaseSummary

# https://coderpad.io/blog/development/sqlalchemy-with-postgresql/

if __name__ == "__main__":
    url = URL.create(
        drivername="postgresql+psycopg2",
        username="postgres",
        password="qqq123",
        host="192.168.1.3",
        database="amos"
    )

    engine = create_engine(url)
    conn = engine.connect()

    Session = sessionmaker(bind=engine)
    session = Session()

    for data_row in session.query(DatabaseSummary).all():
        pass
