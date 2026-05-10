import oracledb
from db.database_helper import OracleDatabase


class BankTransfer:
    def __init__(self, db: OracleDatabase):
        self.db = db

    def run(self):
        customerId = int(input("Customer ID: "))

        customerAccounts = self.getCustomerAccounts(customerId)
        if not customerAccounts:
            print("No accounts found for this customer.")
            return

        print("\nYour accounts:")
        selectedSource = self.selectFromList(
            customerAccounts,
            lambda a: f"{a['iban']}  {a['accountType'].strip():<16}  Balance: {a['balance']} EUR"
        )
        if selectedSource is None:
            print("Invalid selection.")
            return

        sourceIban = selectedSource["iban"]
        sourceAccountType = selectedSource["accountType"].strip()

        if sourceAccountType == "AKTIENDEPOT":
            print("Cannot transfer from a stock depot.")
            return

        print("\nTarget:")
        print("  [1] Own account")
        print("  [2] External IBAN")
        targetChoice = input("Select: ").strip()

        if targetChoice == "1":
            ownTransferableAccounts = [
                a for a in customerAccounts
                if a["iban"] != sourceIban and a["accountType"].strip() != "AKTIENDEPOT"
            ]
            if not ownTransferableAccounts:
                print("No other accounts available.")
                return
            print("\nTarget accounts:")
            selectedTarget = self.selectFromList(
                ownTransferableAccounts,
                lambda a: f"{a['iban']}  {a['accountType'].strip()}"
            )
            if selectedTarget is None:
                print("Invalid selection.")
                return
            targetIban = selectedTarget["iban"]
            targetBic = ""
        elif targetChoice == "2":
            targetIban = input("Target IBAN: ")
            targetBic = input("Target BIC: ")
        else:
            print("Invalid selection.")
            return

        amount = float(input("Amount (EUR): "))
        transferText = input("Purpose: ")

        with self.db.conn.cursor() as cursor:
            cursor.execute("SAVEPOINT before_transfer")

        lockedBalance = self.lockSourceAccount(sourceIban)
        if lockedBalance is None:
            print("Account is locked by another session.")
            return

        if sourceAccountType == "SPARKONTO":
            linkedIban = self.getLinkedIban(sourceIban)
            if targetIban != linkedIban:
                self.db.conn.rollback()
                print(f"Savings account can only transfer to its linked checking account ({linkedIban}).")
                return

        targetAccountType = self.getTargetAccountType(targetIban)
        isInternal = targetAccountType is not None

        if isInternal:
            if targetAccountType.strip() == "AKTIENDEPOT":
                self.db.conn.rollback()
                print("Cannot transfer to a stock depot.")
                return
            if targetAccountType.strip() == "SPARKONTO":
                targetLinkedIban = self.getLinkedIban(targetIban)
                if targetLinkedIban != sourceIban:
                    self.db.conn.rollback()
                    print("Cannot transfer to another customer's savings account.")
                    return

        transType = "T" if isInternal else "P"

        if lockedBalance < amount:
            self.db.conn.rollback()
            print(f"Insufficient funds. Balance: {lockedBalance} EUR, Amount: {amount} EUR")
            return

        print(f"\nFrom:    {sourceIban}")
        print(f"To:      {targetIban}")
        print(f"Amount:  {amount} EUR")
        print(f"Purpose: {transferText}")
        confirm = input("Confirm? (y/n): ")

        if confirm.lower() != "y":
            self.db.conn.rollback()
            return

        self.executeTransfer(sourceIban, targetIban, targetBic, amount, transferText, transType, isInternal)
        print(f"New balance: {lockedBalance - amount} EUR")

    def selectFromList(self, items, labelFn):
        for i, item in enumerate(items):
            print(f"  [{i + 1}] {labelFn(item)}")
        try:
            choice = int(input("Select: ")) - 1
        except ValueError:
            return None
        if choice < 0 or choice >= len(items):
            return None
        return items[choice]

    def getCustomerAccounts(self, customerId):
        with self.db.conn.cursor() as cursor:
            cursor.execute(
                """SELECT iban, account_type, balance FROM ACCOUNT
                   WHERE customer_customer_id = :cid
                   ORDER BY account_type, iban""",
                {"cid": customerId}
            )
            rows = cursor.fetchall()
            return [{"iban": row[0], "accountType": row[1], "balance": row[2]} for row in rows]

    def getSourceAccount(self, customerId, sourceIban):
        with self.db.conn.cursor() as cursor:
            cursor.execute(
                "SELECT account_type FROM ACCOUNT WHERE iban = :iban AND CUSTOMER_customer_id = :cid",
                {"iban": sourceIban, "cid": customerId}
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return row[0]

    def lockSourceAccount(self, sourceIban):
        try:
            with self.db.conn.cursor() as cursor:
                cursor.execute(
                    "SELECT balance FROM ACCOUNT WHERE iban = :iban FOR UPDATE NOWAIT",
                    {"iban": sourceIban}
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

    def getLinkedIban(self, iban):
        with self.db.conn.cursor() as cursor:
            cursor.execute(
                "SELECT ACCOUNT_iban FROM ACCOUNT WHERE iban = :iban",
                {"iban": iban}
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return row[0]

    def getTargetAccountType(self, targetIban):
        with self.db.conn.cursor() as cursor:
            cursor.execute(
                "SELECT account_type FROM ACCOUNT WHERE iban = :iban",
                {"iban": targetIban}
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return row[0]

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

    def executeTransfer(self, sourceIban, targetIban, targetBic, amount, transferText, transType, isInternal):
        try:
            with self.db.conn.cursor() as cursor:
                srcStmtId = self.getOpenStatementId(sourceIban)

                transIdVar = cursor.var(oracledb.NUMBER)
                cursor.execute(
                    """INSERT INTO TRANSACTIONS (transaction_id, valuta_date, amount, ts, purpose,
                       BANK_STATEMENT_statement_id, ACCOUNT_iban, transaction_type)
                       VALUES (SEQ_TRANSACTION_ID.NEXTVAL, TRUNC(SYSDATE), :amount, SYSTIMESTAMP,
                               :purpose, :stmtId, :iban, :type)
                       RETURNING transaction_id INTO :tid""",
                    {"amount": amount, "purpose": transferText, "stmtId": srcStmtId,
                     "iban": sourceIban, "type": transType, "tid": transIdVar}
                )
                srcTransId = int(transIdVar.getvalue()[0])

                if not isInternal:
                    cursor.execute(
                        """INSERT INTO PAYMENT_TRANSACTION (transaction_id, target_iban, target_bic, target_account_iban)
                           VALUES (:tid, :tgtIban, :tgtBic, NULL)""",
                        {"tid": srcTransId, "tgtIban": targetIban, "tgtBic": targetBic if targetBic else None}
                    )

                cursor.execute(
                    "UPDATE ACCOUNT SET balance = balance - :amount WHERE iban = :iban",
                    {"amount": amount, "iban": sourceIban}
                )

                cursor.execute(
                    """UPDATE BANK_STATEMENT SET withdrawal_sum = withdrawal_sum + :amount,
                       withdrawal_count = withdrawal_count + 1,
                       ending_balance = ending_balance - :amount
                       WHERE statement_id = :stmtId""",
                    {"amount": amount, "stmtId": srcStmtId}
                )

                if isInternal:
                    tgtStmtId = self.getOpenStatementId(targetIban)

                    cursor.execute(
                        """INSERT INTO TRANSACTIONS (transaction_id, valuta_date, amount, ts, purpose,
                           BANK_STATEMENT_statement_id, ACCOUNT_iban, transaction_type)
                           VALUES (SEQ_TRANSACTION_ID.NEXTVAL, TRUNC(SYSDATE), :amount, SYSTIMESTAMP,
                                   :purpose, :stmtId, :iban, :type)""",
                        {"amount": amount, "purpose": transferText, "stmtId": tgtStmtId,
                         "iban": targetIban, "type": transType}
                    )

                    cursor.execute(
                        "UPDATE ACCOUNT SET balance = balance + :amount WHERE iban = :iban",
                        {"amount": amount, "iban": targetIban}
                    )

                    cursor.execute(
                        """UPDATE BANK_STATEMENT SET deposit_sum = deposit_sum + :amount,
                           deposit_count = deposit_count + 1,
                           ending_balance = ending_balance + :amount
                           WHERE statement_id = :stmtId""",
                        {"amount": amount, "stmtId": tgtStmtId}
                    )

            self.db.conn.commit()
            print("Transfer successful.")

        except oracledb.DatabaseError as e:
            self.db.conn.rollback()
            print(f"Transfer failed: {e}")
