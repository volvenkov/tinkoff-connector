class AccountNotFoundException(Exception):
    pass


def get_account_id(client, account_name: str) -> str | None:
    account_id = None

    for account in client.users.get_accounts().accounts:
        if account.name == account_name:
            account_id = account.id

    return account_id
