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
        if ":" in ip:
            host, port = ip.rsplit(":", 1)
            s.connect((host, int(port)))
        else:
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
    if ip:
        PEERS.add(ip)
        save_peers()
        log.info(f"Connected to peer: {ip}")
        _send(ip, {"type": "PEER", "data": ip})
        # Request their chain on connect
        _send(ip, {"type": "HELLO", "height": len(data["chain"])})
        send_chain_to_peer(ip, data)

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
                    log.info(f"Block {blk['index']} accepted from {addr[0]}")
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
