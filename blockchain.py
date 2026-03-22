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
    for block in data["chain"]:
        apply_block_utxo(block)
    save_utxo()
    log.info(f"UTXO rebuilt: {len(UTXO)} entries")

def apply_block_utxo(block):
    for tx in block["tx"]:
        if tx["from"] != "COINBASE":
            for inp in tx.get("inputs", []):
                UTXO.pop(inp, None)
    for tx in block["tx"]:
        txid = tx.get("txid") or tx_hash(tx)
        UTXO[txid] = {"address": tx["to"], "amount": tx["amount"]}
    log.debug(f"UTXO after block {block['index']}: {len(UTXO)} entries")

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
    log.info(f"Block {height} mined in {elapsed}s nonce={block['nonce']} reward={reward/DECIMALS:.8f} URN")
    with chain_lock:
        data["chain"].append(block)
        data["pending"] = [t for t in data["pending"] if t not in included]
        data["total_supply"] = calculate_total_supply(data["chain"])
        apply_block_utxo(block)
        save_chain(data)
        save_utxo()
        adjust_difficulty(data)
    return block
