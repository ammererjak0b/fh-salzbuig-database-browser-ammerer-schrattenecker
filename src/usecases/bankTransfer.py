from db.database_helper import OracleDatabase


class BankTransfer:
    def __init__(self, db: OracleDatabase):
        self.db = db

    def run(self):
        print("Bank Transfer not implemented yet")
