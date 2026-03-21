#!/usr/bin/env python3
# Run this once: python setup.py
# It will create all URN node files correctly

import os

files = {}

files["config.py"] = '''
import json, os
CONFIG_FILE = "settings.json"
DEFAULTS = {
    "coin": {"name":"Uranium","ticker":"URN","decimals":100000000,"max_supply":15000000,"initial_reward":32,"halving_interval":50000},
    "mining": {"difficulty":5,"target_block_time":30,"adjust_interval":10,"max_block_tx":1000,"coinbase_maturity":0,"max_future_time":120},
    "mempool": {"max_tx":5000,"fee":0.1},
    "network": {"p2p_port":5000,"api_port":8080,"bootstrap_nodes":[]},
    "files": {"wallet":"wallet.json","backup":"wallet_backup.json","chain":"chain.json","peers":"peers.json","utxo":"utxo.json","log":"urn.log"}
}
def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE) as f:
                user = json.load(f)
            cfg = json.loads(json.dumps(DEFAULTS))
            for section, values in user.items():
                if section in cfg and isinstance(values, dict):
                    cfg[section].update(values)
                else:
                    cfg[section] = values
            return cfg
        except:
            pass
    with open(CONFIG_FILE, "w") as f:
        json.dump(DEFAULTS, f, indent=2)
    return json.loads(json.dumps(DEFAULTS))
CFG = load_config()
DECIMALS          = CFG["coin"]["decimals"]
MAX_SUPPLY        = CFG["coin"]["max_supply"] * DECIMALS
INITIAL_REWARD    = CFG["coin"]["initial_reward"] * DECIMALS
HALVING_INTERVAL  = CFG["coin"]["halving_interval"]
DIFFICULTY        = CFG["mining"]["difficulty"]
TARGET_BLOCK_TIME = CFG["mining"]["target_block_time"]
ADJUST_INTERVAL   = CFG["mining"]["adjust_interval"]
MAX_BLOCK_TX      = CFG["mining"]["max_block_tx"]
COINBASE_MATURITY = CFG["mining"]["coinbase_maturity"]
MAX_FUTURE_TIME   = CFG["mining"]["max_future_time"]
MAX_MEMPOOL_TX    = CFG["mempool"]["max_tx"]
FEE               = int(CFG["mempool"]["fee"] * DECIMALS)
P2P_PORT          = CFG["network"]["p2p_port"]
API_PORT          = CFG["network"]["api_port"]
BOOTSTRAP_NODES   = CFG["network"]["bootstrap_nodes"]
WALLET_FILE       = CFG["files"]["wallet"]
BACKUP_FILE       = CFG["files"]["backup"]
CHAIN_FILE        = CFG["files"]["chain"]
PEER_FILE         = CFG["files"]["peers"]
UTXO_FILE         = CFG["files"]["utxo"]
LOG_FILE          = CFG["files"]["log"]
'''.strip()

files["utils.py"] = '''
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
'''.strip()

files["wallet.py"] = '''
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
    print("\\n Creating new URN wallet...")
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
    log.info(f"Wallet created: {w[\'address\']}")
    print(f"Wallet created! Address: {w[\'address\']}")
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
'''.strip()

files["blockchain.py"] = '''
import json, time, hashlib, secrets, threading
from config import (
    DECIMALS, MAX_SUPPLY, INITIAL_REWARD, HALVING_INTERVAL,
    DIFFICULTY, TARGET_BLOCK_TIME, ADJUST_INTERVAL,
    MAX_BLOCK_TX, COINBASE_MATURITY, MAX_FUTURE_TIME,
    MAX_MEMPOOL_TX, FEE, CHAIN_FILE, UTXO_FILE
)
from utils import sha256, merkle_root, log

UTXO        = {}
_difficulty = DIFFICULTY
chain_lock  = threading.Lock()

def load_chain():
    try:
        with open(CHAIN_FILE) as f:
            d = json.load(f)
        if not d.get("chain"):
            raise ValueError("empty")
        return d
    except:
        log.warning("Chain file missing - starting fresh")
        d = {"chain": [_genesis()], "pending": [], "total_supply": 0}
        save_chain(d)
        return d

def save_chain(d):
    with open(CHAIN_FILE, "w") as f:
        json.dump(d, f)

def load_utxo():
    global UTXO
    try:
        with open(UTXO_FILE) as f:
            UTXO = json.load(f)
        log.debug(f"UTXO loaded: {len(UTXO)} entries")
    except:
        log.warning("UTXO missing - will rebuild")
        UTXO = {}

def save_utxo():
    with open(UTXO_FILE, "w") as f:
        json.dump(UTXO, f)

def _genesis():
    g = {"index":0,"time":1700000000.0,"tx":[],"merkle":sha256(""),"prev":"0"*64,"nonce":0}
    g["hash"] = block_hash(g)
    return g

def block_hash(b):
    raw = json.dumps({"index":b["index"],"time":b["time"],"tx":b["tx"],"merkle":b.get("merkle",""),"prev":b["prev"],"nonce":b["nonce"]}, sort_keys=True)
    first = hashlib.sha256(raw.encode()).digest()
    return hashlib.sha256(first).hexdigest()

def get_difficulty():
    return _difficulty

def adjust_difficulty(data):
    global _difficulty
    height = len(data["chain"])
    if height < ADJUST_INTERVAL or height % ADJUST_INTERVAL != 0:
        return
    first = data["chain"][-ADJUST_INTERVAL]
    last  = data["chain"][-1]
    actual   = last["time"] - first["time"]
    expected = TARGET_BLOCK_TIME * ADJUST_INTERVAL
    if actual < expected / 2:
        _difficulty += 1
        log.info(f"Difficulty up to {_difficulty}")
    elif actual > expected * 2 and _difficulty > 1:
        _difficulty -= 1
        log.info(f"Difficulty down to {_difficulty}")

def validate_chain(chain):
    for i in range(1, len(chain)):
        if chain[i]["prev"] != chain[i-1]["hash"]:
            return False
        if block_hash(chain[i]) != chain[i]["hash"]:
            return False
    return True

def valid_new_block(block, last):
    if block["index"] != last["index"] + 1: return False
    if block["prev"] != last["hash"]: return False
    if block_hash(block) != block["hash"]: return False
    if not block["hash"].startswith("0" * _difficulty): return False
    if block.get("merkle") != merkle_root(block["tx"]): return False
    if block["time"] <= last["time"]: return False
    if block["time"] > time.time() + MAX_FUTURE_TIME: return False
    return True

def choose_chain(local, remote):
    if not validate_chain(remote):
        return local
    if len(remote) > len(local):
        log.info(f"Switching to longer chain remote={len(remote)}")
        return remote
    return local

def rebuild_utxo(data):
    global UTXO
    UTXO = {}
    chain_height = len(data["chain"])
    for block_idx, block in enumerate(data["chain"]):
        for tx in block["tx"]:
            txid = tx.get("txid") or tx_hash(tx)
            if tx["from"] != "COINBASE":
                for inp in tx.get("inputs", []):
                    UTXO.pop(inp, None)
            if tx["from"] == "COINBASE" and COINBASE_MATURITY > 0:
                if (chain_height - block_idx) < COINBASE_MATURITY:
                    continue
            UTXO[txid] = {"address": tx["to"], "amount": tx["amount"]}
    log.info(f"UTXO rebuilt: {len(UTXO)} entries")

def apply_block_utxo(block):
    for tx in block["tx"]:
        txid = tx.get("txid") or tx_hash(tx)
        if tx["from"] != "COINBASE":
            for inp in tx.get("inputs", []):
                UTXO.pop(inp, None)
        UTXO[txid] = {"address": tx["to"], "amount": tx["amount"]}

def get_balance(addr):
    total = sum(u["amount"] for u in UTXO.values() if u["address"] == addr)
    return round(total / DECIMALS, 8)

def get_spendable_utxos(addr):
    return {k: v for k, v in UTXO.items() if v["address"] == addr}

def pending_spent(addr, data):
    return sum(t["amount"] + t["fee"] for t in data["pending"] if t["from"] == addr)

def calculate_total_supply(chain):
    return sum(tx["amount"] for b in chain for tx in b["tx"] if tx["from"] == "COINBASE")

def tx_hash(tx):
    s = json.dumps({"from":tx["from"],"to":tx["to"],"amount":tx["amount"],"fee":tx["fee"],"inputs":tx.get("inputs",[])}, sort_keys=True)
    return hashlib.sha256(s.encode()).hexdigest()

def verify_tx(tx):
    if tx["from"] == "COINBASE":
        return True
    try:
        from wallet import verify_sig
        return verify_sig(tx_hash(tx), tx["sig"], tx["pubkey"])
    except:
        return False

def valid_address(a):
    if len(a) != 40: return False
    try:
        int(a, 16)
        return True
    except:
        return False

def create_transaction(wallet, to, amount_urn, data):
    if not valid_address(to):
        log.warning("Invalid address")
        return None
    if to == wallet["address"]:
        log.warning("Cannot send to yourself")
        return None
    amt = int(amount_urn * DECIMALS)
    if amt <= 0:
        return None
    spendable = get_spendable_utxos(wallet["address"])
    available = sum(u["amount"] for u in spendable.values())
    available -= pending_spent(wallet["address"], data)
    if available < amt + FEE:
        log.warning(f"Insufficient balance: have {available/DECIMALS:.8f}")
        return None
    if len(data["pending"]) >= MAX_MEMPOOL_TX:
        log.warning("Mempool full")
        return None
    inputs, collected = [], 0
    for txid, utxo in spendable.items():
        inputs.append(txid)
        collected += utxo["amount"]
        if collected >= amt + FEE:
            break
    tx_body = {"from":wallet["address"],"to":to,"amount":amt,"fee":FEE,"inputs":inputs}
    from wallet import sign_tx
    sig = sign_tx(tx_hash(tx_body), wallet["private"])
    tx = {**tx_body, "pubkey": wallet["public"], "sig": sig}
    data["pending"].append(tx)
    save_chain(data)
    log.info(f"TX created: {amt/DECIMALS:.8f} URN to {to[:10]}...")
    return tx

def get_reward(height):
    return max(INITIAL_REWARD >> (height // HALVING_INTERVAL), 0)

def mine_block(wallet, data):
    global UTXO
    if not data["chain"] or not validate_chain(data["chain"]):
        log.warning("Cannot mine: chain invalid")
        return None
    clean = [tx for tx in data["pending"] if verify_tx(tx)]
    dropped = len(data["pending"]) - len(clean)
    if dropped:
        log.warning(f"Dropped {dropped} invalid TX(s)")
    data["pending"] = clean
    height  = len(data["chain"])
    reward  = get_reward(height)
    current = calculate_total_supply(data["chain"])
    if current + reward > MAX_SUPPLY:
        reward = 0
    included = data["pending"][:MAX_BLOCK_TX]
    total_fees = sum(tx["fee"] for tx in included)
    coinbase = {
        "from": "COINBASE",
        "to": wallet["address"],
        "amount": reward + total_fees,
        "fee": 0,
        "inputs": [],
        "txid": sha256("COINBASE" + wallet["address"] + str(reward) + str(time.time()) + secrets.token_hex(8))
    }
    txs = included + [coinbase]
    block = {
        "index": height,
        "time": time.time(),
        "tx": txs,
        "merkle": merkle_root(txs),
        "prev": data["chain"][-1]["hash"],
        "nonce": 0
    }
    log.info(f"Mining block {height} difficulty={_difficulty}...")
    start = time.time()
    target = "0" * _difficulty
    while True:
        h = block_hash(block)
        if h.startswith(target):
            block["hash"] = h
            break
        block["nonce"] += 1
    elapsed = round(time.time() - start, 2)
    log.info(f"Block {height} mined in {elapsed}s nonce={block[\'nonce\']} reward={reward/DECIMALS:.8f} URN")
    with chain_lock:
        data["chain"].append(block)
        data["pending"] = [t for t in data["pending"] if t not in included]
        data["total_supply"] = calculate_total_supply(data["chain"])
        apply_block_utxo(block)
        save_chain(data)
        save_utxo()
        adjust_difficulty(data)
    return block
'''.strip()

files["network.py"] = '''
import json, socket, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from config import P2P_PORT, API_PORT, PEER_FILE
from utils import recv_all, send_msg, send_json, log
from blockchain import (
    valid_new_block, choose_chain, validate_chain,
    rebuild_utxo, apply_block_utxo, save_chain, save_utxo,
    calculate_total_supply, verify_tx, get_balance,
    get_difficulty, chain_lock, UTXO, MAX_MEMPOOL_TX
)

PEERS   = set()
syncing = False

def load_peers():
    global PEERS
    try:
        with open(PEER_FILE) as f:
            PEERS = set(json.load(f))
        log.info(f"Loaded {len(PEERS)} peers")
    except:
        PEERS = set()

def save_peers():
    with open(PEER_FILE, "w") as f:
        json.dump(list(PEERS), f)

def _send(ip, obj):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(5)
        s.connect((ip, P2P_PORT))
        send_json(s, obj)
        s.close()
    except:
        pass

def broadcast(obj, exclude=None):
    for ip in list(PEERS):
        if ip != exclude:
            _send(ip, obj)

def send_hello(ip, height):
    _send(ip, {"type": "HELLO", "height": height})

def broadcast_tx(tx):
    broadcast({"type": "TX", "data": tx})

def broadcast_block(block):
    broadcast({"type": "BLOCK", "data": block})

def broadcast_chain(data):
    broadcast({"type": "CHAIN", "data": data})

def broadcast_mempool(pending):
    broadcast({"type": "MEMPOOL", "data": pending})

def send_chain_to_peer(ip, data):
    _send(ip, {"type": "CHAIN", "data": data})

def connect_peer(ip, data):
    if ip and ip not in PEERS:
        PEERS.add(ip)
        save_peers()
        log.info(f"Connected to peer: {ip}")
        _send(ip, {"type": "PEER", "data": ip})
        send_chain_to_peer(ip, data)
        send_hello(ip, len(data["chain"]))

def start_p2p(data):
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", P2P_PORT))
    srv.listen(50)
    log.info(f"P2P listening on port {P2P_PORT}")

    def handle(conn, addr):
        global syncing
        try:
            raw = recv_all(conn)
            if not raw:
                return
            obj = json.loads(raw.decode())
            t = obj.get("type")

            if t == "HELLO":
                peer_ip = addr[0]
                PEERS.add(peer_ip)
                save_peers()
                peer_h = obj.get("height", 0)
                my_h = len(data["chain"])
                if peer_h > my_h:
                    send_chain_to_peer(peer_ip, data)
                else:
                    send_hello(peer_ip, my_h)
                broadcast({"type":"PEERS","data":list(PEERS)}, exclude=peer_ip)

            elif t == "PEERS":
                for p in obj.get("data", []):
                    if isinstance(p, str):
                        PEERS.add(p)
                save_peers()

            elif t == "PEER":
                ip = obj.get("data")
                if isinstance(ip, str) and ip not in PEERS:
                    PEERS.add(ip)
                    save_peers()
                    log.info(f"Discovered peer: {ip}")

            elif t == "TX":
                tx = obj.get("data", {})
                if not verify_tx(tx):
                    return
                if tx not in data["pending"] and len(data["pending"]) < MAX_MEMPOOL_TX:
                    data["pending"].append(tx)
                    save_chain(data)
                    broadcast_tx(tx)

            elif t == "MEMPOOL":
                for tx in obj.get("data", []):
                    if verify_tx(tx) and tx not in data["pending"]:
                        data["pending"].append(tx)
                save_chain(data)

            elif t == "BLOCK":
                blk = obj.get("data", {})
                if not data["chain"]:
                    return
                last = data["chain"][-1]
                if valid_new_block(blk, last) and blk["hash"] not in {b["hash"] for b in data["chain"]}:
                    with chain_lock:
                        data["chain"].append(blk)
                        data["pending"] = []
                        apply_block_utxo(blk)
                        data["total_supply"] = calculate_total_supply(data["chain"])
                        save_chain(data)
                        save_utxo()
                    log.info(f"Block {blk[\'index\']} accepted from {addr[0]}")
                    broadcast_block(blk)
                else:
                    if PEERS:
                        syncing = True
                        send_chain_to_peer(addr[0], data)

            elif t == "CHAIN":
                remote = obj.get("data", {})
                newchain = choose_chain(data["chain"], remote.get("chain", []))
                if newchain is not data["chain"]:
                    with chain_lock:
                        data["chain"] = newchain
                        data["pending"] = []
                        data["total_supply"] = calculate_total_supply(newchain)
                        rebuild_utxo(data)
                        save_chain(data)
                        save_utxo()
                    log.info(f"Chain synced from {addr[0]} height={len(newchain)}")
                syncing = False

        except Exception as e:
            log.debug(f"P2P error {addr[0]}: {e}")
        finally:
            conn.close()

    def accept_loop():
        while True:
            try:
                conn, addr = srv.accept()
                threading.Thread(target=handle, args=(conn, addr), daemon=True).start()
            except:
                pass

    threading.Thread(target=accept_loop, daemon=True).start()

_api_data   = None
_api_wallet = None

class URNHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _respond(self, code, body):
        payload = json.dumps(body, indent=2).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(payload))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        p = self.path.split("?")[0].rstrip("/")
        if p == "/status":
            d = _api_data
            self._respond(200, {"height":len(d["chain"])-1,"total_supply":calculate_total_supply(d["chain"])/100000000,"pending_tx":len(d["pending"]),"peers":len(PEERS),"difficulty":get_difficulty(),"utxo_count":len(UTXO)})
        elif p.startswith("/balance/"):
            addr = p.split("/balance/")[1]
            self._respond(200, {"address":addr,"balance":get_balance(addr)})
        elif p.startswith("/block/"):
            try:
                idx = int(p.split("/block/")[1])
                self._respond(200, _api_data["chain"][idx])
            except:
                self._respond(404, {"error":"not found"})
        elif p == "/mempool":
            self._respond(200, {"count":len(_api_data["pending"]),"txs":_api_data["pending"]})
        elif p == "/peers":
            self._respond(200, {"peers":list(PEERS)})
        else:
            self._respond(404, {"error":"not found"})

    def do_POST(self):
        p = self.path.rstrip("/")
        if p == "/send":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length))
                from blockchain import create_transaction
                tx = create_transaction(_api_wallet, body.get("to",""), float(body.get("amount",0)), _api_data)
                if tx:
                    broadcast_tx(tx)
                    self._respond(200, {"status":"ok"})
                else:
                    self._respond(400, {"error":"failed"})
            except Exception as e:
                self._respond(500, {"error":str(e)})
        elif p == "/connect":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length))
                connect_peer(body.get("ip",""), _api_data)
                self._respond(200, {"status":"ok"})
            except Exception as e:
                self._respond(500, {"error":str(e)})
        else:
            self._respond(404, {"error":"not found"})

def start_api(data, wallet):
    global _api_data, _api_wallet
    _api_data   = data
    _api_wallet = wallet
    server = HTTPServer(("0.0.0.0", API_PORT), URNHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    log.info(f"REST API on http://localhost:{API_PORT}")
'''.strip()

files["main.py"] = '''
#!/usr/bin/env python3
import threading, time, sys
from wallet import load_wallet, backup_wallet, restore_wallet
from blockchain import (
    load_chain, save_chain, load_utxo, rebuild_utxo, save_utxo,
    mine_block, create_transaction, get_balance,
    calculate_total_supply, UTXO, valid_address
)
from network import (
    load_peers, save_peers, start_p2p, start_api,
    connect_peer, broadcast_tx, broadcast_block, broadcast_chain, PEERS
)
from config import MAX_SUPPLY, DECIMALS, BOOTSTRAP_NODES
from utils import log

_automine_running = False
_automine_thread  = None
_automine_pause   = 5

def _automine_loop(wallet, data):
    global _automine_running
    log.info("Auto-miner started")
    print("\\n  Auto-miner started - type automine stop to stop\\n")
    while _automine_running:
        try:
            block = mine_block(wallet, data)
            if block:
                broadcast_block(block)
                broadcast_chain(data)
                bal = get_balance(wallet["address"])
                print(f"\\n  Block {block[\'index\']} mined! Balance: {bal:.8f} URN")
                print("urn> ", end="", flush=True)
            time.sleep(_automine_pause)
        except Exception as e:
            log.error(f"Automine error: {e}")
            time.sleep(2)
    print("\\n  Auto-miner stopped\\n")

def start_automine(wallet, data):
    global _automine_running, _automine_thread
    if _automine_running:
        print("  Already running")
        return
    _automine_running = True
    _automine_thread = threading.Thread(target=_automine_loop, args=(wallet,data), daemon=True)
    _automine_thread.start()

def stop_automine():
    global _automine_running
    if not _automine_running:
        print("  Not running")
        return
    _automine_running = False
    print("  Stopping after current block...")

HELP = """
Commands:
  bal                 - show balance
  send                - send URN
  mine                - mine one block
  automine start      - start auto-mining
  automine stop       - stop auto-mining
  automine status     - check status
  automine pause <s>  - set pause seconds
  history             - block history
  mytx                - your transactions
  pending             - mempool
  supply              - total supply
  status              - node status
  peers               - list peers
  connect             - add peer
  wallet              - wallet info
  backup              - backup wallet
  restore             - restore wallet
  help                - this menu
  exit                - quit
"""

def main():
    global _automine_pause
    autostart = "--automine" in sys.argv
    print("\\n=== URN TESTNET NODE v2.1 ===")
    wallet = load_wallet()
    data   = load_chain()
    load_peers()
    load_utxo()
    if not UTXO:
        rebuild_utxo(data)
        save_utxo()
    start_p2p(data)
    start_api(data, wallet)
    for ip in list(PEERS):
        connect_peer(ip, data)
    for ip in BOOTSTRAP_NODES:
        connect_peer(ip, data)
    print(f"  Address : {wallet[\'address\']}")
    print(f"  Balance : {get_balance(wallet[\'address\']):.8f} URN")
    print(f"  Height  : {len(data[\'chain\']) - 1}")
    print("  Type help for commands\\n")
    if autostart:
        start_automine(wallet, data)
    while True:
        try:
            cmd = input("urn> ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            stop_automine()
            print("\\nGoodbye!")
            break
        if not cmd:
            continue
        elif cmd == "help":
            print(HELP)
        elif cmd == "bal":
            print(f"  Balance: {get_balance(wallet[\'address\']):.8f} URN")
        elif cmd == "wallet":
            print(f"  Address : {wallet[\'address\']}")
            print(f"  Balance : {get_balance(wallet[\'address\']):.8f} URN")
            print(f"  Public  : {wallet[\'public\'][:32]}...")
        elif cmd == "send":
            to = input("  To: ").strip()
            if not valid_address(to):
                print("  Invalid address")
            else:
                try:
                    amt = float(input("  Amount: ").strip())
                    tx = create_transaction(wallet, to, amt, data)
                    if tx:
                        broadcast_tx(tx)
                        print("  Transaction submitted!")
                    else:
                        print("  Failed - check balance")
                except:
                    print("  Invalid amount")
        elif cmd == "mine":
            if _automine_running:
                print("  Stop automine first")
            else:
                block = mine_block(wallet, data)
                if block:
                    broadcast_block(block)
                    broadcast_chain(data)
                    print(f"  Block {block[\'index\']} mined!")
                    print(f"  Balance: {get_balance(wallet[\'address\']):.8f} URN")
        elif cmd == "automine start":
            start_automine(wallet, data)
        elif cmd == "automine stop":
            stop_automine()
        elif cmd == "automine status":
            state = "RUNNING" if _automine_running else "STOPPED"
            print(f"  Auto-miner: {state} | pause={_automine_pause}s")
        elif cmd.startswith("automine pause "):
            try:
                secs = int(cmd.split("automine pause ")[1])
                _automine_pause = max(0, secs)
                print(f"  Pause set to {_automine_pause}s")
            except:
                print("  Usage: automine pause <seconds>")
        elif cmd == "history":
            for b in data["chain"][1:]:
                print(f"  Block {b[\'index\']} | txs={len(b[\'tx\'])}")
                for t in b["tx"]:
                    print(f"    {t[\'from\'][:10]}.. -> {t[\'to\'][:10]}.. {t[\'amount\']/DECIMALS:.4f} URN")
        elif cmd == "mytx":
            a = wallet["address"]
            found = False
            for b in data["chain"]:
                for t in b["tx"]:
                    if t["from"]==a or t["to"]==a:
                        d = "OUT" if t["from"]==a else "IN "
                        print(f"  [{d}] {t[\'amount\']/DECIMALS:.8f} URN  block={b[\'index\']}")
                        found = True
            if not found:
                print("  No transactions")
        elif cmd == "pending":
            if not data["pending"]:
                print("  Mempool empty")
            else:
                for t in data["pending"]:
                    print(f"  {t[\'from\'][:10]}.. -> {t[\'to\'][:10]}.. {t[\'amount\']/DECIMALS:.4f} URN")
        elif cmd == "supply":
            s = calculate_total_supply(data["chain"])
            print(f"  {s/DECIMALS:.8f} / {MAX_SUPPLY/DECIMALS:.0f} URN ({s/MAX_SUPPLY*100:.4f}%)")
        elif cmd == "status":
            s = calculate_total_supply(data["chain"])
            from blockchain import get_difficulty
            state = "RUNNING" if _automine_running else "STOPPED"
            print(f"  Height    : {len(data[\'chain\'])-1}")
            print(f"  Supply    : {s/DECIMALS:.8f} URN")
            print(f"  Pending   : {len(data[\'pending\'])}")
            print(f"  Peers     : {len(PEERS)}")
            print(f"  Difficulty: {get_difficulty()}")
            print(f"  UTXO      : {len(UTXO)}")
            print(f"  Automine  : {state} pause={_automine_pause}s")
        elif cmd == "peers":
            if not PEERS:
                print("  No peers")
            else:
                [print(f"  {p}") for p in PEERS]
        elif cmd == "connect":
            ip = input("  Peer IP: ").strip()
            connect_peer(ip, data)
        elif cmd == "backup":
            backup_wallet()
        elif cmd == "restore":
            restore_wallet()
        elif cmd == "exit":
            stop_automine()
            print("Goodbye!")
            break
        else:
            print(f"  Unknown: {cmd} - type help")

if __name__ == "__main__":
    main()
'''.strip()

# Write all files
for filename, content in files.items():
    with open(filename, "w") as f:
        f.write(content)
    print(f"  Created {filename}")

print("\nAll files created! Run: python main.py")
