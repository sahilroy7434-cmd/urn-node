import os, json, hashlib, secrets, getpass
from ecdsa import SigningKey, VerifyingKey, SECP256k1, BadSignatureError
from config import WALLET_FILE, BACKUP_FILE
from utils import sha256, log

def _scrypt(password, salt):
    dk = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return dk.hex()

def _enc_key(password, salt):
    return bytes.fromhex(_scrypt(password, salt + b"enc"))

def _xor_bytes(data, key):
    return bytes(a ^ b for a, b in zip(data, key[:len(data)]))

def create_wallet():
    print("\n Creating new URN wallet...")
    pw = getpass.getpass("Set wallet password: ")
    pw2 = getpass.getpass("Confirm password: ")
    if pw != pw2:
        print("Passwords do not match")
        return create_wallet()
    salt = secrets.token_bytes(32)
    sk = SigningKey.generate(curve=SECP256k1)
    vk = sk.get_verifying_key()
    enc_private = _xor_bytes(sk.to_string(), _enc_key(pw, salt)).hex()
    w = {
        "salt": salt.hex(),
        "password": _scrypt(pw, salt),
        "private": enc_private,
        "public": vk.to_string().hex(),
        "address": sha256(vk.to_string().hex())[:40]
    }
    with open(WALLET_FILE, "w") as f:
        json.dump(w, f, indent=2)
    log.info(f"Wallet created: {w['address']}")
    print(f"Wallet created! Address: {w['address']}")
    return _runtime_wallet(w, pw)

def load_wallet():
    if not os.path.exists(WALLET_FILE):
        return create_wallet()
    with open(WALLET_FILE) as f:
        w = json.load(f)
    pw = getpass.getpass("Wallet password: ")
    if "salt" not in w:
        if sha256(pw) != w["password"]:
            print("Wrong password")
            exit(1)
        print("Upgrading wallet to secure format...")
        salt = secrets.token_bytes(32)
        raw_prv = bytes.fromhex(w["private"])
        w_new = {
            "salt": salt.hex(),
            "password": _scrypt(pw, salt),
            "private": _xor_bytes(raw_prv, _enc_key(pw, salt)).hex(),
            "public": w["public"],
            "address": w["address"]
        }
        with open(WALLET_FILE, "w") as f:
            json.dump(w_new, f, indent=2)
        print("Wallet upgraded!")
        return _runtime_wallet(w_new, pw)
    salt = bytes.fromhex(w["salt"])
    if _scrypt(pw, salt) != w["password"]:
        print("Wrong password")
        exit(1)
    return _runtime_wallet(w, pw)

def _runtime_wallet(w, pw):
    salt = bytes.fromhex(w["salt"])
    enc = bytes.fromhex(w["private"])
    dec = _xor_bytes(enc, _enc_key(pw, salt)).hex()
    return {**w, "private": dec}

def backup_wallet():
    if not os.path.exists(WALLET_FILE):
        print("No wallet to back up")
        return
    with open(WALLET_FILE) as f:
        data = json.load(f)
    with open(BACKUP_FILE, "w") as f:
        json.dump(data, f, indent=2)
    print("Wallet backed up!")

def restore_wallet():
    if not os.path.exists(BACKUP_FILE):
        print("No backup found")
        return
    with open(BACKUP_FILE) as f:
        data = json.load(f)
    with open(WALLET_FILE, "w") as f:
        json.dump(data, f, indent=2)
    print("Wallet restored!")

def sign_tx(tx_hash, private_hex):
    sk = SigningKey.from_string(bytes.fromhex(private_hex), curve=SECP256k1)
    return sk.sign(tx_hash.encode()).hex()

def verify_sig(tx_hash, sig_hex, pubkey_hex):
    try:
        vk = VerifyingKey.from_string(bytes.fromhex(pubkey_hex), curve=SECP256k1)
        return vk.verify(bytes.fromhex(sig_hex), tx_hash.encode())
    except:
        return False