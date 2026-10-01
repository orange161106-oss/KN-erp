import pytest


def test_argon2id_hashing_uses_unique_salts_and_verifies(passwords):
    plaintext = " synthetic password "
    first, second = passwords.hash(plaintext), passwords.hash(plaintext)
    assert first.startswith("$argon2id$")
    assert first != second
    assert plaintext not in first
    assert passwords.verify(plaintext, first)
    assert not passwords.verify(plaintext.strip(), first)
    assert not passwords.verify("wrong", first)


@pytest.mark.parametrize("stored_hash", ["invalid", "$argon2id$v=19$m=1,t=1,p=1$broken$broken"])
def test_corrupt_hashes_fail_closed(passwords, stored_hash):
    assert not passwords.verify("any password", stored_hash)
