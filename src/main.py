from db.credentials_helper import CredentialsHelper
from db.database_helper import OracleDatabase
from usecases.stockTransaction import StockTransaction
from usecases.bankTransfer import BankTransfer


def main():
    creds = CredentialsHelper()
    db = OracleDatabase(creds.get_username(), creds.get_password(), creds.get_dsn())
    db.auto_commit(False)

    stockTransaction = StockTransaction(db)
    bankTransfer = BankTransfer(db)

    menu = {
        "1": ("Stock Transaction (Aktienkauf)", stockTransaction.run),
        "2": ("Bank Transfer (Überweisung)", bankTransfer.run),
    }

    while True:
        print("\n--- Bank Application ---")
        for key, (label, _) in menu.items():
            print(f"  {key}. {label}")
        print("  q. Quit")

        choice = input("\nSelect: ").strip().lower()
        if choice == "q":
            break
        elif choice in menu:
            menu[choice][1]()
        else:
            print("Invalid choice.")


if __name__ == "__main__":
    main()
