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