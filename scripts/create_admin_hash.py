from getpass import getpass

import bcrypt

MAX_BCRYPT_PASSWORD_BYTES = 72


def main() -> None:
    password = getpass("Admin password: ")
    confirm = getpass("Confirm password: ")
    if password != confirm:
        raise SystemExit("Passwords do not match")
    password_bytes = password.encode("utf-8")
    if len(password_bytes) > MAX_BCRYPT_PASSWORD_BYTES:
        raise SystemExit("Password is too long for bcrypt; use 72 UTF-8 bytes or fewer.")
    print(bcrypt.hashpw(password_bytes, bcrypt.gensalt(rounds=12)).decode("utf-8"))


if __name__ == "__main__":
    main()
