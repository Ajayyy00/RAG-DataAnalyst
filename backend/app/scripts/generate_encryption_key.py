"""Generate a new Fernet key for PHI encryption at rest.

Usage::

    python -m app.scripts.generate_encryption_key

Add the printed value to PHI_ENCRYPTION_KEYS. To ROTATE, prepend the new key:

    PHI_ENCRYPTION_KEYS=<new-key>,<old-key>

The first key encrypts new data; both decrypt existing data. Once all rows are
re-encrypted (see app/scripts/reencrypt_pii.py), drop the old key.
"""

from cryptography.fernet import Fernet


def main() -> None:
    key = Fernet.generate_key().decode()
    print(key)


if __name__ == "__main__":
    main()
