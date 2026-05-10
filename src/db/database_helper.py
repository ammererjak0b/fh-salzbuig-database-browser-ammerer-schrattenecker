from enum import Enum
from typing import Any
from abc import ABC, abstractmethod
import oracledb


# in oracle isolation levels can be set either on transaction or session level
# we use the transaction level here
# each transaction will start with READ_COMMITTED
# setting isolation level must be the first statement in a transaction
# see https://docs.oracle.com/cd/B28359_01/server.111/b28318/consist.htm#CNCPT1833

class IsolationLevel(Enum):
    READONLY = 1  # read only transaction, no updates allowed, no locks, mostly for reporting
    READ_COMMITTED = 2  # default isolation level, allows updates, locks only on changed rows
    SERIALIZABLE = 3  # Oracle uses SNAPSHOT ISOLATION


class LockMode(Enum):
    SHARED = 1      # shared lock, allows other transactions to read, but not to update it
    EXCLUSIVE = 2   # exclusive lock, allows other transactions neither to read nor to update


# interface for database connection to show how to use abstract classes in python
class IDatabase(ABC):
    @abstractmethod
    def auto_commit(self, autocommit: bool) -> None:
        pass

    @abstractmethod
    def convert2dict(self, cursor) -> None:
        pass

    @abstractmethod
    def set_isolation_level(self, isolation_level: IsolationLevel) -> None:
        pass

    @abstractmethod
    def lock_table(self, table_name: str, lock_mode: LockMode) -> None:
        pass


# class for connecting to oracle database
# this class implements the IDatabase interface
class OracleDatabase(IDatabase):
    # constructor
    # database connection is opened here
    def __init__(self, username: str, password: str, dsn: str, min_conn: int = 1, max_conn: int = 1):
        print(f"about to open database connection to {dsn} with user {username}")
        try:
            self.conn = oracledb.connect(user=username, password=password, dsn=dsn)
        except oracledb.DatabaseError as e:
            print("An error occurred connecting to the database:", e)
            raise e

        # pythonic way to use switch/case
        self.isolation_type_dict = {
            IsolationLevel.READONLY: self._set_readonly,
            IsolationLevel.READ_COMMITTED: self._set_read_committed,
            IsolationLevel.SERIALIZABLE: self._set_serializable
        }

    # destructor
    # close database connection
    def __del__(self):
        # check if connection is still open
        if self.conn is not None:
            self.conn.close()
        print("database connection closed")

    # set autocommit
    def auto_commit(self, autocommit: bool) -> None:
        self.conn.autocommit = autocommit
        pass

    def set_isolation_level(self, isolation_level: IsolationLevel) -> None:
        self.isolation_type_dict[isolation_level]()

    def _set_readonly(self) -> None:
        with (self.conn.cursor() as cursor):
            cursor.execute("SET TRANSACTION READ ONLY");

    def _set_read_committed(self) -> None:
        with (self.conn.cursor() as cursor):
            cursor.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")

    def _set_serializable(self) -> None:
        with (self.conn.cursor() as cursor):
            cursor.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")

    def lock_table(self, table_name: str, lock_mode: LockMode) -> None:
        with (self.conn.cursor() as cursor):
            if lock_mode == LockMode.SHARED:
                cursor.execute(f"LOCK TABLE {table_name} IN SHARE MODE")
            elif lock_mode == LockMode.EXCLUSIVE:
                cursor.execute(f"LOCK TABLE {table_name} IN EXCLUSIVE MODE")
            else:
                raise ValueError("invalid lock mode")

    def convert2dict(self, cursor) -> Any:
        # define a rowfactory that creates a dictionary with the column names, instead of the standard list per row
        # cursor.description contains the column names
        cursor.rowfactory = lambda *args: dict(zip([d[0] for d in cursor.description], args))
