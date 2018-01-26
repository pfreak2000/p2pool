from p2pool.starwels import networks

PARENT = networks.nets['starwels_testnet']
SHARE_PERIOD = 30 # seconds
CHAIN_LENGTH = 60*60//10 # shares
REAL_CHAIN_LENGTH = 60*60//10 # shares
TARGET_LOOKBEHIND = 200 # shares
SPREAD = 3 # blocks
IDENTIFIER = '5fc2be2d4f0d7bfb'.decode('hex')
PREFIX = '3f6057a15036f451'.decode('hex')
P2P_PORT = 19353
MIN_TARGET = 0
MAX_TARGET = 2**256//2**32 - 1
PERSIST = False
WORKER_PORT = 19352
BOOTSTRAP_ADDRS = '163.172.182.145 136.243.39.165 213.159.214.91 94.102.26.117'.split(' ')
ANNOUNCE_CHANNEL = '#p2pool-alt'
VERSION_CHECK = lambda v: 50700 <= v < 60000 or 60010 <= v < 60100 or 60400 <= v
