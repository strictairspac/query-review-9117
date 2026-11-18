import hashlib,secrets,hmac
def hash_password(password):
    salt=secrets.token_hex(16)
    return salt+':'+hashlib.pbkdf2_hmac('sha256',password.encode(),salt.encode(),180000).hex()
def verify(password,encoded):
    salt,digest=encoded.split(':')
    return hmac.compare_digest(digest,hashlib.pbkdf2_hmac('sha256',password.encode(),salt.encode(),180000).hex())
