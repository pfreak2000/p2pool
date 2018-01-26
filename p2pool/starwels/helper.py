import sys
import time

from twisted.internet import defer

import p2pool
from p2pool.starwels import data as starwels_data
from p2pool.util import deferral, jsonrpc

@deferral.retry('Error while checking Starwels connection:', 1)
@defer.inlineCallbacks
def check(starwelsd, net):
    if not (yield net.PARENT.RPC_CHECK(starwelsd)):
        print >>sys.stderr, "    Check failed! Make sure that you're connected to the right starwelsd with --starwelsd-rpc-port!"
        raise deferral.RetrySilentlyException()
    
    version_check_result = net.VERSION_CHECK((yield starwelsd.rpc_getinfo())['version'])
    if version_check_result == True: version_check_result = None # deprecated
    if version_check_result == False: version_check_result = 'Coin daemon too old! Upgrade!' # deprecated
    if version_check_result is not None:
        print >>sys.stderr, '    ' + version_check_result
        raise deferral.RetrySilentlyException()
    
    try:
        blockchaininfo = yield starwelsd.rpc_getblockchaininfo()
        softforks_supported = set(item['id'] for item in blockchaininfo.get('softforks', []))
        try:
            softforks_supported |= set(item['id'] for item in blockchaininfo.get('bip9_softforks', []))
        except TypeError: # https://github.com/starwels/starwels/pull/7863
            softforks_supported |= set(item for item in blockchaininfo.get('bip9_softforks', []))
    except jsonrpc.Error_for_code(-32601): # Method not found
        softforks_supported = set()
    if getattr(net, 'SOFTFORKS_REQUIRED', set()) - softforks_supported:
        print 'Coin daemon too old! Upgrade!'
        raise deferral.RetrySilentlyException()

@deferral.retry('Error getting work from starwelsd:', 3)
@defer.inlineCallbacks
def getwork(starwelsd, use_getblocktemplate=False):
    def go():
        if use_getblocktemplate:
            return starwelsd.rpc_getblocktemplate(dict(mode='template'))
        else:
            return starwelsd.rpc_getmemorypool()
    try:
        start = time.time()
        work = yield go()
        end = time.time()
    except jsonrpc.Error_for_code(-32601): # Method not found
        use_getblocktemplate = not use_getblocktemplate
        try:
            start = time.time()
            work = yield go()
            end = time.time()
        except jsonrpc.Error_for_code(-32601): # Method not found
            print >>sys.stderr, 'Error: Starwels version too old! Upgrade to v0.5 or newer!'
            raise deferral.RetrySilentlyException()
    packed_transactions = [(x['data'] if isinstance(x, dict) else x).decode('hex') for x in work['transactions']]
    if 'height' not in work:
        work['height'] = (yield starwelsd.rpc_getblock(work['previousblockhash']))['height'] + 1
    elif p2pool.DEBUG:
        assert work['height'] == (yield starwelsd.rpc_getblock(work['previousblockhash']))['height'] + 1
    defer.returnValue(dict(
        version=work['version'],
        previous_block=int(work['previousblockhash'], 16),
        transactions=map(starwels_data.tx_type.unpack, packed_transactions),
        transaction_hashes=map(starwels_data.hash256, packed_transactions),
        transaction_fees=[x.get('fee', None) if isinstance(x, dict) else None for x in work['transactions']],
        subsidy=work['coinbasevalue'],
        time=work['time'] if 'time' in work else work['curtime'],
        bits=starwels_data.FloatingIntegerType().unpack(work['bits'].decode('hex')[::-1]) if isinstance(work['bits'], (str, unicode)) else starwels_data.FloatingInteger(work['bits']),
        coinbaseflags=work['coinbaseflags'].decode('hex') if 'coinbaseflags' in work else ''.join(x.decode('hex') for x in work['coinbaseaux'].itervalues()) if 'coinbaseaux' in work else '',
        height=work['height'],
        last_update=time.time(),
        use_getblocktemplate=use_getblocktemplate,
        latency=end - start,
    ))

@deferral.retry('Error submitting primary block: (will retry)', 10, 10)
def submit_block_p2p(block, factory, net):
    if factory.conn.value is None:
        print >>sys.stderr, 'No starwelsd connection when block submittal attempted! %s%064x' % (net.PARENT.BLOCK_EXPLORER_URL_PREFIX, starwels_data.hash256(starwels_data.block_header_type.pack(block['header'])))
        raise deferral.RetrySilentlyException()
    factory.conn.value.send_block(block=block)

@deferral.retry('Error submitting block: (will retry)', 10, 10)
@defer.inlineCallbacks
def submit_block_rpc(block, ignore_failure, starwelsd, starwelsd_work, net):
    if starwelsd_work.value['use_getblocktemplate']:
        try:
            result = yield starwelsd.rpc_submitblock(starwels_data.block_type.pack(block).encode('hex'))
        except jsonrpc.Error_for_code(-32601): # Method not found, for older litecoin versions
            result = yield starwelsd.rpc_getblocktemplate(dict(mode='submit', data=starwels_data.block_type.pack(block).encode('hex')))
        success = result is None
    else:
        result = yield starwelsd.rpc_getmemorypool(starwels_data.block_type.pack(block).encode('hex'))
        success = result
    success_expected = net.PARENT.POW_FUNC(starwels_data.block_header_type.pack(block['header'])) <= block['header']['bits'].target
    if (not success and success_expected and not ignore_failure) or (success and not success_expected):
        print >>sys.stderr, 'Block submittal result: %s (%r) Expected: %s' % (success, result, success_expected)

def submit_block(block, ignore_failure, factory, starwelsd, starwelsd_work, net):
    submit_block_p2p(block, factory, net)
    submit_block_rpc(block, ignore_failure, starwelsd, starwelsd_work, net)

@defer.inlineCallbacks
def check_genesis_block(starwelsd, genesis_block_hash):
    try:
        yield starwelsd.rpc_getblock(genesis_block_hash)
    except jsonrpc.Error_for_code(-5):
        defer.returnValue(False)
    else:
        defer.returnValue(True)
