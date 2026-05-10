import oracledb
from db.database_helper import OracleDatabase


class StockTransaction:
    def __init__(self, db: OracleDatabase):
        self.db = db

    def run(self):
        customerId = int(input("Customer ID: "))
        depotIban = input("Depot IBAN: ")
        isin = input("Stock ISIN: ")
        quantity = int(input("Quantity: "))

        checkingIban = self.getCheckingIban(customerId, depotIban)
        if checkingIban is None:
            print("Depot not found or does not belong to customer.")
            return

        price = self.getStockPrice(isin)
        if price is None:
            print("Stock not found or unavailable.")
            return

        total = quantity * price

        with self.db.conn.cursor() as cursor:
            cursor.execute("SAVEPOINT before_purchase")

        self.reserveStock(isin, quantity)

        balance = self.lockCheckingAccount(checkingIban)
        if balance is None:
            self.db.conn.rollback()
            print("Checking account is locked by another session.")
            return

        if balance < total:
            self.db.conn.rollback()
            print(f"Insufficient funds. Balance: {balance} €, Required: {total} €")
            return

        print(f"\nStock:    {isin}")
        print(f"Quantity: {quantity}")
        print(f"Price:    {price} € per share")
        print(f"Total:    {total} €")
        print(f"Balance:  {balance} €")
        confirm = input("Confirm purchase? (y/n): ")

        if confirm.lower() != "y":
            self.db.conn.rollback()
            return

        self.executePurchase(checkingIban, depotIban, isin, quantity, price, total)

    def getCheckingIban(self, customerId, depotIban):
        with self.db.conn.cursor() as cursor:
            cursor.execute(
                """SELECT ACCOUNT_iban FROM ACCOUNT
                   WHERE iban = :iban
                   AND customer_customer_id = :cid
                   AND account_type = 'AKTIENDEPOT'""",
                {"iban": depotIban, "cid": customerId}
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return row[0]

    def getStockPrice(self, isin):
        with self.db.conn.cursor() as cursor:
            cursor.execute(
                "SELECT price FROM STOCK WHERE isin = :isin AND available_quantity > 0",
                {"isin": isin}
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return row[0]

    def reserveStock(self, isin, quantity):
        with self.db.conn.cursor() as cursor:
            cursor.execute(
                "UPDATE STOCK SET reserved_quantity = reserved_quantity + :qty WHERE isin = :isin",
                {"qty": quantity, "isin": isin}
            )

    def lockCheckingAccount(self, checkingIban):
        try:
            with self.db.conn.cursor() as cursor:
                cursor.execute(
                    "SELECT balance FROM ACCOUNT WHERE iban = :iban FOR UPDATE NOWAIT",
                    {"iban": checkingIban}
                )
                row = cursor.fetchone()
                if row is None:
                    return None
                return row[0]
        except oracledb.DatabaseError as e:
            error = e.args[0]
            if error.code == 54:
                return None
            raise

    def getOpenStatementId(self, iban):
        with self.db.conn.cursor() as cursor:
            cursor.execute(
                "SELECT statement_id FROM BANK_STATEMENT WHERE ACCOUNT_iban = :iban AND status = 'O' AND ROWNUM = 1",
                {"iban": iban}
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return row[0]

    def executePurchase(self, checkingIban, depotIban, isin, quantity, price, total):
        try:
            with self.db.conn.cursor() as cursor:
                stmtId = self.getOpenStatementId(checkingIban)

                transIdVar = cursor.var(oracledb.NUMBER)
                cursor.execute(
                    """INSERT INTO TRANSACTIONS (transaction_id, valuta_date, amount, ts,
                       purpose, BANK_STATEMENT_statement_id, ACCOUNT_iban, transaction_type)
                       VALUES (SEQ_TRANSACTION_ID.NEXTVAL, TRUNC(SYSDATE), :total, SYSTIMESTAMP,
                               :purpose, :stmtId, :iban, 'S')
                       RETURNING transaction_id INTO :tid""",
                    {"total": total, "purpose": "Stock purchase " + isin,
                     "stmtId": stmtId, "iban": checkingIban, "tid": transIdVar}
                )
                transId = int(transIdVar.getvalue()[0])

                cursor.execute(
                    """INSERT INTO STOCK_TRANSACTION (transaction_id, stock_price, stock_quantity, STOCK_isin, depot_iban)
                       VALUES (:tid, :price, :qty, :isin, :depot)""",
                    {"tid": transId, "price": price, "qty": quantity, "isin": isin, "depot": depotIban}
                )

                cursor.execute(
                    """MERGE INTO DEPOT_POSITION dp
                       USING DUAL
                       ON (dp.depot_iban = :depot AND dp.STOCK_isin = :isin AND dp.purchase_date = TRUNC(SYSDATE))
                       WHEN NOT MATCHED THEN
                           INSERT (depot_iban, STOCK_isin, ACCOUNT_iban, purchase_date, purchase_price)
                           VALUES (:depot, :isin, :depot, TRUNC(SYSDATE), :price)""",
                    {"depot": depotIban, "isin": isin, "price": price}
                )

                cursor.execute(
                    "UPDATE ACCOUNT SET balance = balance - :total WHERE iban = :iban",
                    {"total": total, "iban": checkingIban}
                )

                cursor.execute(
                    """UPDATE STOCK SET available_quantity = available_quantity - :qty,
                       reserved_quantity = reserved_quantity - :qty
                       WHERE isin = :isin""",
                    {"qty": quantity, "isin": isin}
                )

                cursor.execute(
                    """UPDATE BANK_STATEMENT SET withdrawal_sum = withdrawal_sum + :total,
                       withdrawal_count = withdrawal_count + 1,
                       ending_balance = ending_balance - :total
                       WHERE statement_id = :stmtId""",
                    {"total": total, "stmtId": stmtId}
                )

            self.db.conn.commit()
            print("Purchase successful.")

        except oracledb.DatabaseError as e:
            self.db.conn.rollback()
            print(f"Purchase failed: {e}")
