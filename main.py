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
    print("\n  Auto-miner started - type 'am stop' to stop\n")
    while _automine_running:
        try:
            block = mine_block(wallet, data)
            if block:
                broadcast_block(block)
                broadcast_chain(data)
                bal = get_balance(wallet["address"])
                print(f"\n  Block {block['index']} mined! Balance: {bal:.8f} URN")
                print("urn> ", end="", flush=True)
            time.sleep(_automine_pause)
        except Exception as e:
            log.error(f"Automine error: {e}")
            time.sleep(2)
    print("\n  Auto-miner stopped\n")

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
  am start            - start auto-mining
  am stop             - stop auto-mining
  ams                 - check status
  amp <s>             - set pause seconds
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
    print("\n=== URN TESTNET NODE v2.1 ===")
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
    print(f"  Address : {wallet['address']}")
    print(f"  Balance : {get_balance(wallet['address']):.8f} URN")
    print(f"  Height  : {len(data['chain']) - 1}")
    print("  Type help for commands\n")
    if autostart:
        start_automine(wallet, data)
    while True:
        try:
            cmd = input("urn> ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            stop_automine()
            print("\nGoodbye!")
            break
        if not cmd:
            continue
        elif cmd == "help":
            print(HELP)
        elif cmd == "bal":
            print(f"  Balance: {get_balance(wallet['address']):.8f} URN")
        elif cmd == "wallet":
            print(f"  Address : {wallet['address']}")
            print(f"  Balance : {get_balance(wallet['address']):.8f} URN")
            print(f"  Public  : {wallet['public'][:32]}...")
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
                    print(f"  Block {block['index']} mined!")
                    print(f"  Balance: {get_balance(wallet['address']):.8f} URN")
        elif cmd == "am start":
            start_automine(wallet, data)
        elif cmd == "am stop":
            stop_automine()
        elif cmd == "ams":
            state = "RUNNING" if _automine_running else "STOPPED"
            print(f"  Auto-miner: {state} | pause={_automine_pause}s")
        elif cmd.startswith("amp "):
            try:
                parts = cmd.strip().split(" ")
                secs = int(parts[-1])
                _automine_pause = max(0, secs)
                print(f"  Pause set to {_automine_pause}s")
            except:
                print("  Usage: amp <seconds>")
        elif cmd == "history":
            for b in data["chain"][1:]:
                print(f"  Block {b['index']} | txs={len(b['tx'])}")
                for t in b["tx"]:
                    print(f"    {t['from'][:10]}.. -> {t['to'][:10]}.. {t['amount']/DECIMALS:.4f} URN")
        elif cmd == "mytx":
            a = wallet["address"]
            found = False
            for b in data["chain"]:
                for t in b["tx"]:
                    if t["from"]==a or t["to"]==a:
                        d = "OUT" if t["from"]==a else "IN "
                        print(f"  [{d}] {t['amount']/DECIMALS:.8f} URN  block={b['index']}")
                        found = True
            if not found:
                print("  No transactions")
        elif cmd == "pending":
            if not data["pending"]:
                print("  Mempool empty")
            else:
                for t in data["pending"]:
                    print(f"  {t['from'][:10]}.. -> {t['to'][:10]}.. {t['amount']/DECIMALS:.4f} URN")
        elif cmd == "supply":
            s = calculate_total_supply(data["chain"])
            print(f"  {s/DECIMALS:.8f} / {MAX_SUPPLY/DECIMALS:.0f} URN ({s/MAX_SUPPLY*100:.4f}%)")
        elif cmd == "status":
            s = calculate_total_supply(data["chain"])
            from blockchain import get_difficulty
            state = "RUNNING" if _automine_running else "STOPPED"
            print(f"  Height    : {len(data['chain'])-1}")
            print(f"  Supply    : {s/DECIMALS:.8f} URN")
            print(f"  Pending   : {len(data['pending'])}")
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
