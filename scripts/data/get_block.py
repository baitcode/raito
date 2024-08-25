import requests
import sys
import os
import json
import progressbar


BTC_RPC = os.getenv("BITCOIN_RPC")
USR = os.getenv("USERPWD")


def request_rpc(method, params):
    payload = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params
    }
    headers = {'content-type': 'application/json'}
    data = requests.post(BTC_RPC, auth=tuple(USR.split(':')), headers=headers, data=json.dumps(payload)).json()
    if data['result'] is None:
        raise ConnectionError("Error recieving data")
    return data['result']


def buid_witness(array):
    witness = str(len(array))
    for elem in array:
        length = len(str(elem)) / 2
        witness += f"{length}{elem}"
    return witness


def header(block):
    return f'''Header {{
                version: {block["version"]}_u32,
                time: {block["time"]}_u32,
                bits: {int(block["bits"], 16)}_u32,
                nonce: {block["nonce"]}_u32,
        }}'''


def tx_output(tx):
    payload = ""
    cached = "false"
    for txoutput in tx['vout']:
        payload += f'''
                    TxOut {{
                        value: {int(txoutput["value"] * 100000000)}_u64,
                        pk_script: @from_hex(\"{txoutput["scriptPubKey"]["hex"]}\"),
                        cached: {cached},
                    }},
                    '''
    return payload


def outpoint(prev_output):
    # full_tx = request_rpc("gettxout", [tx_in["txid"], tx_in["vout"]])
    prev_tx = request_rpc("getrawtransaction", [prev_output['txid'], True])
    prev_block = request_rpc("getblock", [prev_tx['blockhash'], 2])
    return f'''
                                OutPoint {{
                                    txid: 0x{prev_tx['txid']}_u256.into(),
                                    vout: {prev_output['vout']}_u32,
                                    data: {tx_output({'vout': [prev_tx['vout'][prev_output['vout']]]})}
                                    block_height: {prev_block['height']}_u32,
                                    block_time: {prev_block['time']}_u32,
                                }}'''


def tx_input_coinbase(tx_in):
    witness = ""
    if 'txinwitness' in tx_in:
        formatted_elements = [f'from_hex("{elem}")' for elem in tx_in["txinwitness"]]
        witness = ", ".join(formatted_elements)
        # witness = buid_witness(tx_in['txinwitness'])
    return f'''
                    TxIn {{
                        script: @from_hex(\"{tx_in["coinbase"]}\"),
                        sequence: {tx_in["sequence"]},
                        witness: array![{witness}].span(),
                        previous_output: OutPoint {{
                            txid: 0_u256.into(),
                            vout: 0xffffffff_u32,
                            data: Default::default(),
                            block_height: Default::default(),
                            block_time: Default::default(),
                        }},
                    }}'''


def tx_input_regular(tx_in):
    witness = ""
    if 'txinwitness' in tx_in:
        # witness = buid_witness(tx_in['txinwitness'])
        formatted_elements = [f'from_hex("{elem}")' for elem in tx_in["txinwitness"]]
        witness = ", ".join(formatted_elements)
    return f'''
                        TxIn {{
                            script: @from_hex(\"{tx_in["scriptSig"]['hex']}\"),
                            sequence: {tx_in["sequence"]},
                            witness: array![{witness}].span(),
                            previous_output: {outpoint(tx_in)},
                        }},
                        '''


def tx_input(tx):
    payload = ""
    for txinput in tx['vin']:
        if 'coinbase' in txinput:
            payload += tx_input_coinbase(txinput)
        else:
            payload += tx_input_regular(txinput)
    return payload


def check_segwit(tx):
    if not int(tx["version"]) % 2:
        return "true"
    return "false"


def txs_process(txsraw, ntx):
    payload = ''
    bar = progressbar.ProgressBar(max_value=ntx)
    bar.update(0)
    for i, tx in enumerate(txsraw):
        payload += f'''
            Transaction {{
                version: {tx["version"]},
                is_segwit: {check_segwit(tx)},
                lock_time: {tx["locktime"]},
                inputs: array![{tx_input(tx)}].span(),
                outputs: array![{tx_output(tx)}].span(),
                }},
                '''
        bar.update(i + 1)
    return payload


def main():
    try:
        if (len(sys.argv) != 2):
            raise TypeError("Error: bad arguments")
        block_hash = sys.argv[1]

        block = request_rpc("getblock", [block_hash, 2])
        txsraw = block["tx"]

        file_payload = f'''// THIS CODE IS GENERATED BY SCRIPT, DO NOT EDIT IT MANUALLY
use raito::state::{{Block, Header, Transaction, TxIn, TxOut, OutPoint}};
use raito::utils::hex::from_hex;
use raito::utils::hash::Hash;

// block_hash: {block_hash}
pub fn block_{block["height"]}() -> Block {{
    Block {{
        header: {header(block)},
        txs: array![{txs_process(txsraw, block["nTx"])}].span(),
    }}
}}'''

        path = f'tests/blocks/block_{block["height"]}.cairo'
        print(block["height"])
        file = open(path, "w")
        file.write(file_payload)
        file.close()
    except Exception as error:
        print(error)


main()