# The MIT License (MIT)
# Copyright (c) 2021-2024 Krux contributors

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
from ur.ur import UR
from embit.descriptor.descriptor import Descriptor
from embit.descriptor.arguments import Key, KeyOrigin
from embit.networks import NETWORKS
from .krux_settings import t
from .key import P2PKH, P2SH_P2WPKH, P2WPKH, P2WSH, P2TR


class AssumptionWarning(Exception):
    """An exception for assumptions that require user acceptance"""


class Wallet:
    """Represents the wallet that the current key belongs to"""

    def __init__(self, key):
        self.key = key
        self.wallet_data = None
        self.wallet_qr_format = None
        self.descriptor = None
        self.label = None
        self.policy = None
        self.persisted = None
        self._network = None
        if self.key and not self.key.multisig:
            if self.key.script_type == P2PKH:
                self.descriptor = Descriptor.from_string(
                    "pkh(%s/<0;1>/*)" % self.key.key_expression()
                )
            elif self.key.script_type == P2SH_P2WPKH:
                self.descriptor = Descriptor.from_string(
                    "sh(wpkh(%s/<0;1>/*))" % self.key.key_expression()
                )
            elif self.key.script_type == P2WPKH:
                self.descriptor = Descriptor.from_string(
                    "wpkh(%s/<0;1>/*)" % self.key.key_expression()
                )

            elif self.key.script_type == P2TR:
                self.descriptor = Descriptor.from_string(
                    "tr(%s/<0;1>/*)" % self.key.key_expression()
                )
            self.label = t("Single-sig")
            self.policy = {"type": self.descriptor.scriptpubkey_type()}

    @property
    def network(self):
        """Returns network from user's current wallet, else from the descriptor"""
        if self._network is None:
            if self.key:
                self._network = [
                    k for k, v in NETWORKS.items() if v == self.key.network
                ][0]
            else:
                version = self.descriptor.keys[0].key.version
                for k, v in NETWORKS.items():
                    if version in v.values():
                        self._network = k
                        break
        return self._network

    def is_multisig(self):
        """Returns a boolean indicating whether or not the wallet is multisig"""
        if self.key:
            return self.key.multisig
        if self.descriptor:
            return self.descriptor.is_basic_multisig
        return None

    def is_loaded(self):
        """Returns a boolean indicating whether or not this wallet has been loaded"""
        return self.wallet_data is not None

    def load(self, wallet_data, qr_format, allow_assumptions=False):
        """Loads the wallet from the given data"""
        descriptor, label = parse_wallet(wallet_data, allow_assumptions)

        if self.key:
            if self.is_multisig():
                if not descriptor.is_basic_multisig:
                    raise ValueError("not multisig")
                if self.key.xpub() not in [
                    key.key.to_base58() for key in descriptor.keys
                ]:
                    raise ValueError("xpub not a cosigner")
            else:
                if not descriptor.key:
                    if len(descriptor.keys) > 1:
                        raise ValueError("not single-sig")
                if self.key.xpub() != descriptor.key.key.to_base58():
                    raise ValueError("xpub does not match")

        self.wallet_data = wallet_data
        self.wallet_qr_format = qr_format
        self.descriptor = to_unambiguous_descriptor(descriptor)
        self.label = label

        if self.descriptor.key:
            if not self.label:
                self.label = t("Single-sig")
            self.policy = {"type": self.descriptor.scriptpubkey_type()}
        else:
            m = int(str(self.descriptor.miniscript.args[0]))
            n = len(self.descriptor.keys)
            cosigners = [key.key.to_base58() for key in self.descriptor.keys]
            if self.descriptor.is_sorted:
                cosigners = sorted(cosigners)
            if not self.label:
                self.label = t("%d of %d multisig") % (m, n)
            self.policy = {
                "type": self.descriptor.scriptpubkey_type(),
                "m": m,
                "n": n,
                "cosigners": cosigners,
            }

    def wallet_qr(self):
        """Returns the original wallet data and qr format for display back as a QR code"""
        return (self.wallet_data, self.wallet_qr_format)

    def obtain_addresses(self, i=0, limit=None, branch_index=0):
        """Returns an iterator deriving addresses (default branch_index is receive)
        for the wallet up to the provided limit"""
        starting_index = i

        while limit is None or i < starting_index + limit:
            yield self.descriptor.derive(i, branch_index=branch_index).address(
                network=NETWORKS[self.network]
            )
            i += 1


def to_unambiguous_descriptor(descriptor):
    """If child derivation info is missing to generate receive addresses,
    use the default scheme
    """
    from embit.descriptor.arguments import KeyHash, AllowedDerivation

    if descriptor.key:
        if descriptor.key.allowed_derivation is None:
            descriptor.key.allowed_derivation = AllowedDerivation.default()
    else:
        for i in range(len(descriptor.miniscript.args)):
            key = descriptor.miniscript.args[i]
            if isinstance(key, (Key, KeyHash)):
                if key.allowed_derivation is None:
                    key.allowed_derivation = AllowedDerivation.default()
    return descriptor


def parse_wallet(wallet_data, allow_assumptions=False):
    """Exhaustively tries to parse the wallet data from a known format, returning
    a descriptor and label if possible.

    If the descriptor cannot be derived, an exception is raised.
    """
    # pylint: disable=R0912

    import urtypes

    if isinstance(wallet_data, UR):
        # Try to parse as a Crypto-Output type
        try:
            output = urtypes.crypto.Output.from_cbor(wallet_data.cbor)
            return Descriptor.from_string(output.descriptor()), None
        except:
            pass

        # Treat the UR as a generic UR bytes object and extract the data for further processing
        wallet_data = urtypes.Bytes.from_cbor(wallet_data.cbor).data

    # Process as a string
    wallet_data = (
        wallet_data.decode() if not isinstance(wallet_data, str) else wallet_data
    )

    # Try to parse as JSON and look for a 'descriptor' key
    try:
        try:
            import ujson as json
        except ImportError:
            import json

        wallet_json = json.loads(wallet_data)
        if "descriptor" in wallet_json:
            descriptor = Descriptor.from_string(wallet_json["descriptor"])
            label = wallet_json["label"] if "label" in wallet_json else None
            return descriptor, label
        raise KeyError('"descriptor" key not found in JSON')
    except KeyError:
        raise ValueError("invalid wallet format")
    except:
        pass

    # Try to parse as a key-value file
    try:
        key_vals = []
        for word in wallet_data.split(":"):
            for key_val in word.split("\n"):
                key_val = key_val.strip()
                if key_val != "":
                    key_vals.append(key_val)

        keys_present = [key in key_vals for key in ["Format", "Policy", "Derivation"]]
        if any(keys_present):
            if not all(keys_present):
                raise KeyError(
                    '"Format", "Policy", and "Derivation" keys not found in INI file'
                )

            script = key_vals[key_vals.index("Format") + 1].lower()
            if script != P2WSH:
                raise ValueError("invalid script type: %s" % script)

            policy = key_vals[key_vals.index("Policy") + 1]
            m = int(policy[: policy.index("of")].strip())
            n = int(policy[policy.index("of") + 2 :].strip())

            keys = []
            for i in range(len(key_vals)):
                xpub = key_vals[i]
                if xpub.lower().startswith("xpub") or xpub.lower().startswith("tpub"):
                    fingerprint = key_vals[i - 1]
                    keys.append((xpub, fingerprint))

            if len(keys) != n:
                raise ValueError("expected %d keys, found %d" % (n, len(keys)))

            derivation = key_vals[key_vals.index("Derivation") + 1]

            keys.sort()
            keys = ["[%s/%s]%s" % (key[1], derivation[2:], key[0]) for key in keys]
            if len(keys) > 1:
                descriptor = Descriptor.from_string(
                    ("wsh(sortedmulti(%d," % m) + ",".join(keys) + "))"
                )
            else:
                # Single-sig - assuming Native Segwit
                descriptor = Descriptor.from_string("wpkh(%s/<0;1>/*)" % keys[0])
            label = (
                key_vals[key_vals.index("Name") + 1]
                if key_vals.index("Name") >= 0
                else None
            )
            return descriptor, label
    except:
        raise ValueError("invalid wallet format")

    # Try to parse directly as a descriptor
    try:
        descriptor = Descriptor.from_string(wallet_data.strip())
        return descriptor, None
    except:
        # If that fails, try to parse as an xpub as a last resort
        pubkey = Key.from_string(wallet_data.strip())
        if pubkey.is_extended:
            network, versiontype = version_to_network_versiontype(pubkey.key.version)

            xpub = pubkey.key.to_base58(version=NETWORKS[network]["xpub"])

            if pubkey.origin is None:
                # assume Key.origin if possible
                derivation = xpub_data_to_derivation(
                    versiontype,
                    network,
                    pubkey.key.child_number,
                    pubkey.key.depth,
                    allow_assumptions=allow_assumptions,
                )
                if derivation:
                    pubkey.origin = KeyOrigin(b"\x00" * 4, derivation)

            fmt = None
            if pubkey.origin:
                fmt = key_origin_to_script_wrapper(pubkey.origin)

            descriptor = Descriptor.from_string(fmt.format(xpub))
            return descriptor, None

    raise ValueError("invalid wallet format")


def parse_address(address_data):
    """Exhaustively tries to parse an address from a known format, returning
    the address if possible.

    If the address cannot be derived, an exception is raised.
    """
    from embit.script import Script, address_to_scriptpubkey

    addr = address_data
    if address_data.lower().startswith("bitcoin:"):
        addr_end = address_data.find("?")
        if addr_end == -1:
            addr_end = len(address_data)
        addr = address_data[8:addr_end]

    try:
        sc = address_to_scriptpubkey(addr)
        assert isinstance(sc, Script)
    except:
        raise ValueError("invalid address")

    return addr


def version_to_network_versiontype(hdkey_version):
    """returns embit.networks.NETWORKS[network][versiontype] keys
    based on HDKey's version bytes"""
    network, versiontype = None, None
    for netname, versiontypes in NETWORKS.items():
        if hdkey_version in versiontypes.values():
            network = netname
            versiontype = [k for k, v in versiontypes.items() if v == hdkey_version][0]
            break
    return network, versiontype


def xpub_data_to_derivation(
    versiontype, network, child, depth, allow_assumptions=False
):
    """returns assumed derivation list for supported slip32 bips
    based on embit.networks.NETWORKS keys for versiontype, network,
    child_number (used as account for single-sig) and depth.  Depth
    is used as weak verification, it must match the expected depth.
    Where unsafe assumptions could be made, AssumptionError is raised
    unless called with allow_assumptions=True.
    """

    derivation, network_node, assumption_text = None, None, None

    if network == "main":
        network_node = 0 + 2**31
    elif network in ("test", "regtest", "signet"):
        network_node = 1 + 2**31

    if network_node and child >= 2**31:
        if versiontype == "xpub" and depth == 3:
            if allow_assumptions:
                derivation = [44 + 2**31, network_node, child]
            else:
                assumption_text = t("Legacy - 44 (p2pkh) would be assumed")
        elif versiontype == "ypub" and depth == 3:
            derivation = [49 + 2**31, network_node, child]
        elif versiontype == "zpub" and depth == 3:
            derivation = [84 + 2**31, network_node, child]
        elif versiontype == "Ypub" and depth == 4 and child == 1 + 2**31:
            if allow_assumptions:
                derivation = [48 + 2**31, network_node, 0 + 2**31, child]
            else:
                assumption_text = t("Account #0 would be assumed")
        elif versiontype == "Zpub" and depth == 4 and child == 2 + 2**31:
            if allow_assumptions:
                derivation = [48 + 2**31, network_node, 0 + 2**31, child]
            else:
                assumption_text = t("Account #0 would be assumed")

    if assumption_text:
        raise AssumptionWarning(assumption_text)

    return derivation


def key_origin_to_script_wrapper(key_origin):
    """returns format_str for wrapping xpub into wallet descriptor,
    based on embit.descriptor.arguments.KeyOrigin"""
    format_str = None
    purpose = key_origin.derivation[0]
    if purpose == 44 + 2**31:
        format_str = "pkh([%s]{})" % key_origin
    elif purpose == 49 + 2**31:
        format_str = "sh(wpkh([%s]{}))" % key_origin
    elif purpose == 84 + 2**31:
        format_str = "wpkh([%s]{})" % key_origin
    elif purpose == 86 + 2**31:
        format_str = "tr([%s]{})" % key_origin
    return format_str
