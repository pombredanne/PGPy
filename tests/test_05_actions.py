""" test doing things with keys/signatures/etc
"""
import pytest

import glob
import os
import time

from contextlib import contextmanager
from datetime import datetime, timedelta
from warnings import catch_warnings

from pgpy import PGPKey
from pgpy import PGPMessage
from pgpy import PGPSignature
from pgpy import PGPUID

from pgpy.constants import CompressionAlgorithm
from pgpy.constants import Features
from pgpy.constants import HashAlgorithm
from pgpy.constants import ImageEncoding
from pgpy.constants import KeyFlags
from pgpy.constants import KeyServerPreferences
from pgpy.constants import PubKeyAlgorithm
from pgpy.constants import RevocationReason
from pgpy.constants import SignatureType
from pgpy.constants import SymmetricKeyAlgorithm
from pgpy.constants import TrustLevel


from pgpy.errors import PGPDecryptionError
from pgpy.errors import PGPError


def _read(f, mode='r'):
    with open(f, mode) as ff:
        return ff.read()


class TestPGPMessage(object):
    params = {
        'comp_alg': [ CompressionAlgorithm.Uncompressed, CompressionAlgorithm.ZIP, CompressionAlgorithm.ZLIB,
                      CompressionAlgorithm.BZ2 ],
        'enc_msg':  [ PGPMessage.from_file(f) for f in glob.glob('tests/testdata/messages/message*.pass*.asc') ],
        'file':    ['tests/testdata/lit', 'tests/testdata/lit2', 'tests/testdata/lit_de']
    }
    attrs = {
        'tests/testdata/lit':
            [('filename', 'lit'),
             ('message', os.linesep.join(['This is stored, literally\!', os.linesep]))],
        'tests/testdata/lit2':
            [('filename', 'lit2'),
             ('message', os.linesep.join(['This is stored, literally!', os.linesep]))],
        'tests/testdata/lit_de':
            [('filename', 'lit_de'),
             ('message', os.linesep.join(['The following items are stored, literally:', '- This one', '- Also this one',
                                          '- And finally, this one!', os.linesep]))],
    }
    def test_new(self, comp_alg, write_clean, gpg_print):
        msg = PGPMessage.new("This is a new message!")

        assert msg.type == 'literal'
        assert msg.message == "This is a new message!"
        assert msg._message.format == 't'
        assert msg._message.filename == ''

        with write_clean('tests/testdata/cmsg.asc', 'w', str(msg)):
            assert gpg_print('cmsg.asc') == "This is a new message!"

    def test_new_sensitive(self, write_clean, gpg_print):
        msg = PGPMessage.new("This is a sensitive message!", sensitive=True)

        assert msg.type == 'literal'
        assert msg.message == "This is a sensitive message!"
        assert msg.is_sensitive
        assert msg.filename == '_CONSOLE'

        with write_clean('tests/testdata/csmsg.asc', 'w', str(msg)):
            assert gpg_print('csmsg.asc') == "This is a sensitive message!"

    def test_new_from_file(self, file, write_clean, gpg_print):
        msg = PGPMessage.new(file, file=True)

        assert isinstance(msg, PGPMessage)
        assert msg.type == 'literal'
        assert msg.is_sensitive is False

        assert file in self.attrs
        for attr, expected in self.attrs[file]:
            val = getattr(msg, attr)
            assert val == expected

        with write_clean('tests/testdata/cmsg.asc', 'w', str(msg)):
            assert gpg_print('cmsg.asc') == msg.message

    def test_decrypt_passphrase_message(self, enc_msg):
        decmsg = enc_msg.decrypt("QwertyUiop")

        assert isinstance(decmsg, PGPMessage)
        assert decmsg.message == b"This is stored, literally\\!\n\n"

    def test_encrypt_passphrase(self, write_clean, gpg_decrypt):
        msg = PGPMessage.new("This message is to be encrypted")
        encmsg = msg.encrypt("QwertyUiop")

        # make sure lit was untouched
        assert not msg.is_encrypted

        # make sure encmsg is encrypted
        assert encmsg.is_encrypted
        assert encmsg.type == 'encrypted'

        # decrypt with PGPy
        decmsg = encmsg.decrypt("QwertyUiop")

        assert isinstance(decmsg, PGPMessage)
        assert decmsg.type == msg.type
        assert decmsg.is_compressed
        assert decmsg.message == msg.message

        # decrypt with GPG
        with write_clean('tests/testdata/semsg.asc', 'w', str(encmsg)):
            assert gpg_decrypt('./semsg.asc', "QwertyUiop") == "This message is to be encrypted"

    def test_encrypt_passphrase_2(self, write_clean, gpg_decrypt):
        msg = PGPMessage.new("This message is to be encrypted")
        sk = SymmetricKeyAlgorithm.AES256.gen_key()
        encmsg = msg.encrypt("QwertyUiop", sessionkey=sk).encrypt("AsdfGhjkl", sessionkey=sk)

        # make sure lit was untouched
        assert not msg.is_encrypted

        # make sure encmsg is encrypted
        assert encmsg.is_encrypted
        assert encmsg.type == 'encrypted'
        assert len(encmsg._sessionkeys) == 2

        # decrypt with PGPy
        for passphrase in ["QwertyUiop", "AsdfGhjkl"]:
            decmsg = encmsg.decrypt(passphrase)
            assert isinstance(decmsg, PGPMessage)
            assert decmsg.type == msg.type
            assert decmsg.is_compressed
            assert decmsg.message == msg.message


@pytest.fixture(scope='module')
def string():
    return "This string will be signed"


@pytest.fixture(scope='module')
def message():
    return PGPMessage.new("This is a message!", compression=CompressionAlgorithm.Uncompressed)


@pytest.fixture(scope='module')
def ctmessage():
    return PGPMessage.new("This is a cleartext message!", cleartext=True)


@pytest.fixture(scope='module')
def targette_pub():
    return PGPKey.from_file('tests/testdata/keys/targette.pub.rsa.asc')[0]


@pytest.fixture(scope='module')
def targette_sec():
    return PGPKey.from_file('tests/testdata/keys/targette.sec.rsa.asc')[0]


@pytest.fixture(scope='module')
def userid():
    return PGPUID.new('Abraham Lincoln', comment='Honest Abe', email='abraham.lincoln@whitehouse.gov')


@pytest.fixture(scope='module')
def userphoto():
    with open('tests/testdata/abe.jpg', 'rb') as abef:
        abebytes = bytearray(os.path.getsize('tests/testdata/abe.jpg'))
        abef.readinto(abebytes)
    return PGPUID.new(abebytes)


@pytest.fixture(scope='module')
def sessionkey():
    # return SymmetricKeyAlgorithm.AES128.gen_key()
    return b'\x9d[\xc1\x0e\xec\x01k\xbc\xf4\x04UW\xbb\xfb\xb2\xb9'


class TestPGPKey(object):
    params = {
        'pub':        [ PGPKey.from_file(f)[0] for f in sorted(glob.glob('tests/testdata/keys/*.pub.asc')) ],
        'sec':        [ PGPKey.from_file(f)[0] for f in sorted(glob.glob('tests/testdata/keys/*.sec.asc')) ],
        'enc':        [ PGPKey.from_file(f)[0] for f in sorted(glob.glob('tests/testdata/keys/*.enc.asc')) ],
        'sigkey':     [ PGPKey.from_file(f)[0] for f in sorted(glob.glob('tests/testdata/signatures/*.key.asc')) ],
        'sigsig':     [ PGPSignature.from_file(f) for f in sorted(glob.glob('tests/testdata/signatures/*.sig.asc')) ],
        'sigsubj':    sorted(glob.glob('tests/testdata/signatures/*.subj')),
        'key_alg':    [ PubKeyAlgorithm.RSAEncryptOrSign, PubKeyAlgorithm.DSA ]
    }
    string_sigs = dict()
    timestamp_sigs = dict()
    standalone_sigs = dict()
    encmessage = []

    @contextmanager
    def assert_warnings(self):
        with catch_warnings(record=True) as w:
            try:
                yield

            finally:
                for warning in w:
                    try:
                        assert warning.filename == __file__

                    except AssertionError as e:
                        e.args += (warning.message,)
                        raise

    def test_new(self):
        pytest.skip("not implemented yet")

    def test_protect(self):
        pytest.skip("not implemented yet")

    def test_unlock(self, enc, sec):
        assert enc.is_protected
        assert enc.is_unlocked is False
        assert sec.is_protected is False

        # unlock with the correct passphrase
        with enc.unlock('QwertyUiop') as _unlocked, self.assert_warnings():
            assert _unlocked is enc
            assert enc.is_unlocked

    def test_verify_detached(self, sigkey, sigsig, sigsubj):
        assert sigkey.verify(_read(sigsubj), sigsig)

    def test_sign_string(self, sec, string, write_clean, gpg_import, gpg_verify):
        with self.assert_warnings():
            # add all of the subpackets we should be allowed to
            sig = sec.sign(string,
                           user=sec.userids[0].name,
                           expires=timedelta(seconds=1),
                           revocable=False,
                           notation={'Testing': 'This signature was generated during unit testing'},
                           policy_uri='about:blank')

        # wait a bit if sig is not yet expired
        assert sig.type == SignatureType.BinaryDocument
        assert sig.notation == {'Testing': 'This signature was generated during unit testing'}
        assert sig.revocable is False
        assert sig.policy_uri == 'about:blank'
        # assert sig.sig.signer_uid == "{:s}".format(sec.userids[0])
        assert next(iter(sig._signature.subpackets['SignersUserID'])).userid == "{:s}".format(sec.userids[0])
        if not sig.is_expired:
            time.sleep((sig.expires_at - datetime.utcnow()).total_seconds())
        assert sig.is_expired

        # verify with GnuPG
        with write_clean('tests/testdata/string', 'w', string), \
                write_clean('tests/testdata/string.asc', 'w', str(sig)), \
                gpg_import('./pubtest.asc'):
            assert gpg_verify('./string', './string.asc', keyid=sig.signer)

        self.string_sigs[sec.fingerprint.keyid] = sig

    def test_verify_string(self, pub, string):
        sig = self.string_sigs.pop(pub.fingerprint.keyid)
        with self.assert_warnings():
            sv = pub.verify(string, signature=sig)

        assert sv
        assert len(sv) == 1

    def test_sign_ctmessage(self, sec, ctmessage, write_clean, gpg_import, gpg_verify):
        expire_at = datetime.utcnow() + timedelta(days=1)
        assert isinstance(expire_at, datetime)

        with self.assert_warnings():
            sig = sec.sign(ctmessage, expires=expire_at)

        assert sig.type == SignatureType.CanonicalDocument
        assert sig.revocable
        assert sig.is_expired is False

        ctmessage |= sig

        # verify with GnuPG
        with write_clean('tests/testdata/ctmessage.asc', 'w', str(ctmessage)), gpg_import('./pubtest.asc'):
            assert gpg_verify('./ctmessage.asc', keyid=sig.signer)

    def test_verify_ctmessage(self, pub, ctmessage):
        with self.assert_warnings():
            sv = pub.verify(ctmessage)

        assert sv
        assert len(sv) > 0

    def test_sign_message(self, sec, message):
        with self.assert_warnings():
            sig = sec.sign(message)

        assert sig.type == SignatureType.BinaryDocument
        assert sig.revocable
        assert sig.is_expired is False

        message |= sig

    def test_verify_message(self, pub, message):
        with self.assert_warnings():
            sv = pub.verify(message)

        assert sv
        assert len(sv) > 0

    def test_gpg_verify_message(self, message, write_clean, gpg_import, gpg_verify):
        # verify with GnuPG
        with write_clean('tests/testdata/message.asc', 'w', str(message)), gpg_import('./pubtest.asc'):
            assert gpg_verify('./message.asc')

    def test_encrypt_message(self, pub, message, sessionkey):
        if pub.key_algorithm != PubKeyAlgorithm.RSAEncryptOrSign:
            pytest.skip('Asymmetric encryption only implemented for RSA currently')
            return

        if len(self.encmessage) == 1:
            message = self.encmessage.pop(0)

        with self.assert_warnings():
            enc = pub.encrypt(message, sessionkey=sessionkey, cipher=SymmetricKeyAlgorithm.AES128)
            self.encmessage.append(enc)

    def test_decrypt_encmessage(self, sec, message):
        if sec.key_algorithm != PubKeyAlgorithm.RSAEncryptOrSign:
            pytest.skip('Asymmetric encryption only implemented for RSA currently')
            return

        encmessage = self.encmessage[0]

        with self.assert_warnings():
            decmsg = sec.decrypt(encmessage)

        assert decmsg.message == message.message

    def test_gpg_decrypt_encmessage(self, write_clean, gpg_import, gpg_decrypt):
        emsg = self.encmessage.pop(0)
        with write_clean('tests/testdata/aemsg.asc', 'w', str(emsg)), gpg_import('./sectest.asc'):
            assert gpg_decrypt('./aemsg.asc', keyid='EEE097A017B979CA')

    def test_sign_timestamp(self, sec):
        with self.assert_warnings():
            sig = sec.sign(None)

        assert sig.type == SignatureType.Timestamp
        self.timestamp_sigs[sec.fingerprint.keyid] = sig

    def test_verify_timestamp(self, pub):
        sig = self.timestamp_sigs.pop(pub.fingerprint.keyid)
        with self.assert_warnings():
            sv = pub.verify(None, sig)

        assert sv
        assert len(sv) > 0

    def test_sign_standalone(self, sec):
        with self.assert_warnings():
            sig = sec.sign(None, notation={"cheese status": "standing alone"})

        assert sig.type == SignatureType.Standalone
        assert sig.notation == {"cheese status": "standing alone"}
        self.standalone_sigs[sec.fingerprint.keyid] = sig

    def test_verify_standalone(self, pub):
        sig = self.standalone_sigs.pop(pub.fingerprint.keyid)
        with self.assert_warnings():
            sv = pub.verify(None, sig)

        assert sv
        assert len(sv) > 0

    def test_add_userid(self, userid, targette_sec):
        # add userid to targette_sec
        expire_in = datetime.utcnow() + timedelta(days=2)
        with self.assert_warnings():
            # add all of the subpackets that only work on self-certifications
            targette_sec.add_uid(userid,
                                 usage=[KeyFlags.Certify, KeyFlags.Sign],
                                 ciphers=[SymmetricKeyAlgorithm.AES256, SymmetricKeyAlgorithm.Camellia256],
                                 hashes=[HashAlgorithm.SHA384],
                                 compression=[CompressionAlgorithm.ZLIB],
                                 key_expiration=expire_in,
                                 keyserver_flags=0x80,
                                 keyserver='about:none',
                                 primary=False)

        sig = userid.selfsig

        assert sig.type == SignatureType.Positive_Cert
        assert sig.cipherprefs == [SymmetricKeyAlgorithm.AES256, SymmetricKeyAlgorithm.Camellia256]
        assert sig.hashprefs == [HashAlgorithm.SHA384]
        assert sig.compprefs == [CompressionAlgorithm.ZLIB]
        assert sig.features == {Features.ModificationDetection}
        assert sig.key_expiration == expire_in - targette_sec.created
        assert sig.keyserver == 'about:none'
        assert sig.keyserverprefs == [KeyServerPreferences.NoModify]

        assert userid.is_primary is False

    def test_remove_userid(self, targette_sec):
        # create a temporary userid, add it, and then remove it
        tempuid = PGPUID.new('Temporary Youx\'seur')
        targette_sec.add_uid(tempuid)

        assert tempuid in targette_sec

        targette_sec.del_uid('Temporary Youx\'seur')
        assert tempuid not in targette_sec

    def test_certify_userid(self, sec, userid):
        with self.assert_warnings():
            # add all of the subpackets that only work on (non-self) certifications
            sig = sec.certify(userid, SignatureType.Casual_Cert,
                              usage=KeyFlags.Authentication,
                              exportable=True,
                              trust=(1, 60),
                              regex=r'.*')

        assert sig.type == SignatureType.Casual_Cert
        assert sig.key_flags == {KeyFlags.Authentication}
        assert sig.exportable
        # assert sig.trust_level == 1
        # assert sig.trust_amount == 60
        # assert sig.regex == r'.*'

        assert {sec.fingerprint.keyid} | set(sec.subkeys) & userid.signers

        userid |= sig

    def test_verify_userid(self, pub, userid):
        # with PGPy
        with self.assert_warnings():
            sv = pub.verify(userid)

        assert sv
        assert len(sv) > 0

    def test_add_photo(self, userphoto, targette_sec):
        with self.assert_warnings():
            targette_sec.add_uid(userphoto)

    def test_certify_photo(self, sec, userphoto):
        with self.assert_warnings():
            userphoto |= sec.certify(userphoto)

    def test_revoke_certification(self, sec, userphoto):
        # revoke the certifications of userphoto
        with self.assert_warnings():
            revsig = sec.revoke(userphoto)

        assert revsig.type == SignatureType.CertRevocation

        userphoto |= revsig

    def test_certify_key(self, sec, targette_sec):
        # let's add an 0x1f signature with notation
        # GnuPG does not like these, so we'll mark it as non-exportable
        with self.assert_warnings():
            sig = sec.certify(targette_sec, exportable=False, notation={'Notice': 'This key has been frobbed!',
                                                                        'Binary': bytearray(b'\xc0\x01\xd0\x0d')})

        assert sig.type == SignatureType.DirectlyOnKey
        assert sig.exportable is False
        assert sig.notation == {'Notice': 'This key has been frobbed!', 'Binary': bytearray(b'\xc0\x01\xd0\x0d')}

        targette_sec |= sig

    def test_self_certify_key(self, targette_sec):
        # let's add an 0x1f signature with notation
        with self.assert_warnings():
            sig = targette_sec.certify(targette_sec, notation={'Notice': 'This key has been self-frobbed!'})

        assert sig.type == SignatureType.DirectlyOnKey
        assert sig.notation == {'Notice': 'This key has been self-frobbed!'}

        targette_sec |= sig

    def test_add_revocation_key(self, sec, targette_sec):
        targette_sec |= targette_sec.revoker(sec)

    def test_verify_key(self, pub, targette_sec):
        with self.assert_warnings():
            sv = pub.verify(targette_sec)
            assert len(list(sv.good_signatures)) > 0
            assert sv

    def test_new_key(self, key_alg):
        pytest.skip("not implemented yet")

    def test_new_subkey(self):
        pytest.skip("not implemented yet")

    def test_add_subkey(self):
        # when this is implemented, it will replace the temporary test_bind_subkey below
        # and test_revoke_subkey will be rewritten
        pytest.skip("not implemented yet")

    def test_gpg_verify_key(self, targette_sec, write_clean, gpg_import, gpg_check_sigs):
        # with GnuPG
        with write_clean('tests/testdata/targette.sec.asc', 'w', str(targette_sec)), \
                gpg_import('./pubtest.asc', './targette.sec.asc') as kio:
            assert 'invalid self-signature' not in kio
            assert gpg_check_sigs(targette_sec.fingerprint.keyid)

    def test_bind_subkey(self, sec, pub, write_clean, gpg_import, gpg_check_sigs):
        # this is temporary, until subkey generation works
        # replace the first subkey's binding signature with a new one
        subkey = next(iter(pub.subkeys.values()))
        old_usage = next(sig for sig in subkey._signatures if sig.type == SignatureType.Subkey_Binding).key_flags
        subkey._signatures.clear()

        with self.assert_warnings():
            bsig = sec.bind(subkey, usage=old_usage)

            assert bsig.type == SignatureType.Subkey_Binding
            assert 'EmbeddedSignature' in bsig._signature.subpackets

            subkey |= bsig
            assert len([sig for sig in subkey._signatures if sig.type == SignatureType.Subkey_Binding]) == \
                    len([sig for sig in subkey._signatures if sig.type == SignatureType.PrimaryKey_Binding])

            assert {SignatureType.Subkey_Binding, SignatureType.PrimaryKey_Binding} <= {sig.type for sig in subkey._signatures}
            assert all(sig.embedded for sig in subkey._signatures if sig.type == SignatureType.PrimaryKey_Binding)

            # verify with PGPy
            sv = pub.verify(subkey)
            assert bsig in iter(s.signature for s in sv._subjects)
            assert sv
            sv = pub.verify(pub)
            assert bsig in iter(s.signature for s in sv._subjects)
            assert sv

        # verify with GPG
        kfp = '{:s}.asc'.format(pub.fingerprint.shortid)
        with write_clean(os.path.join('tests', 'testdata', kfp), 'w', str(pub)), \
                gpg_import(os.path.join('.', kfp)) as kio:
            assert 'invalid self-signature' not in kio
            assert gpg_check_sigs(pub.fingerprint.keyid, subkey.fingerprint.keyid)

    def test_revoke_key(self, sec, pub, write_clean, gpg_import, gpg_check_sigs):
        with self.assert_warnings():
            rsig = sec.revoke(pub, sigtype=SignatureType.KeyRevocation, reason=RevocationReason.Retired,
                            comment="But you're so oooold")
            assert 'ReasonForRevocation' in rsig._signature.subpackets
            pub |= rsig

            # verify with PGPy
            # assert pub.verify(pub)

        # verify with GPG
        kfp = '{:s}.asc'.format(pub.fingerprint.shortid)
        with write_clean(os.path.join('tests', 'testdata', kfp), 'w', str(kfp)), \
                gpg_import(os.path.join('.', kfp)) as kio:
            assert 'invalid self-signature' not in kio

        # and remove it, for good measure
        pub._signatures.remove(rsig)
        assert rsig not in pub

    def test_revoke_key_with_revoker(self):
        pytest.skip("not implemented yet")

    def test_revoke_subkey(self, sec, pub, write_clean, gpg_import, gpg_check_sigs):
        subkey = next(iter(pub.subkeys.values()))
        with self.assert_warnings():
            # revoke the first subkey
            rsig = sec.revoke(subkey, sigtype=SignatureType.SubkeyRevocation)
            assert 'ReasonForRevocation' in rsig._signature.subpackets
            subkey |= rsig

            # # verify with PGPy
            assert pub.verify(subkey)
            sv = pub.verify(pub)
            assert sv
            assert rsig in iter(s.signature for s in sv.good_signatures)

        # verify with GPG
        kfp = '{:s}.asc'.format(pub.fingerprint.shortid)
        with write_clean(os.path.join('tests', 'testdata', kfp), 'w', str(kfp)), \
                gpg_import(os.path.join('.', kfp)) as kio:
            assert 'invalid self-signature' not in kio

        # and remove it, for good measure
        subkey._signatures.remove(rsig)
        assert rsig not in subkey
