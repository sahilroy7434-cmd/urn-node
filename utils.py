import hashlib, json, logging, os
from config import LOG_FILE

def setup_logger():
    logger = logging.getLogger("URN")
    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter("[%(asctime)s] %(levelname)s  %(message)s", "%Y-%m-%d %H:%M:%S")
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)
    fh = logging.FileHandler(LOG_FILE)
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    return logger

log = setup_logger()

def sha256(s):
    return hashlib.sha256(s.encode()).hexdigest()

def sha256b(b):
    return hashlib.sha256(b).hexdigest()

def merkle_root(txs):
    if not txs:
        return sha256("")
    layer = [sha256(json.dumps(tx, sort_keys=True)) for tx in txs]
    while len(layer) > 1:
        if len(layer) % 2 == 1:
            layer.append(layer[-1])
        layer = [sha256(layer[i] + layer[i+1]) for i in range(0, len(layer), 2)]
    return layer[0]

def recv_all(conn):
    try:
        raw_len = b""
        while len(raw_len) < 8:
            chunk = conn.recv(8 - len(raw_len))
            if not chunk:
                return b""
            raw_len += chunk
        msg_len = int.from_bytes(raw_len, "big")
        if msg_len > 50000000:
            return b""
        data = b""
        while len(data) < msg_len:
            chunk = conn.recv(min(65536, msg_len - len(data)))
            if not chunk:
                break
            data += chunk
        return data
    except:
        return b""

def send_msg(conn, payload):
    conn.sendall(len(payload).to_bytes(8, "big") + payload)

def send_json(conn, obj):
    send_msg(conn, json.dumps(obj).encode())