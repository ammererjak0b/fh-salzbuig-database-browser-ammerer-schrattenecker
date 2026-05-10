from db.database_helper import OracleDatabase


class StockTransaction:
    def __init__(self, db: OracleDatabase):
        self.db = db

    def run(self):
        print("Stock Transaction not implemented yet")
