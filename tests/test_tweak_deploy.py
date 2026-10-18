"""Exercise SSH upload/install arguments and password input without a device."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

class TweakDeployTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='md deploy ')
        self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name)
        self.log = self.work / 'calls'
        self.package = self.work / 'a package.deb'
        self.package.write_bytes(b'fixture deb')
        self.key = self.work / 'a key'
        self.key.touch()
        ssh = self.work / 'ssh'
        ssh.write_text('''#!/usr/bin/python3
import json,os,sys
command=sys.argv[-1]
data=sys.stdin.buffer.read() if command.startswith('cat >') or 'sudo -S' in command else b''
with open(os.environ['CALL_LOG'],'a') as f:
 f.write(json.dumps({'args':sys.argv[1:],'stdin':data.decode(),'secret_env':bool(os.environ.get('SSHPASS'))})+'\\n')
if command.startswith('mktemp'):print('/tmp/monkeydev-tweak.ABCD12')
if 'dpkg -i' in command:sys.exit(int(os.environ.get('INSTALL_STATUS','0')))
''')
        ssh.chmod(0o755)
        sshpass = self.work / 'sshpass'
        sshpass.write_text('#!/bin/bash\n[[ "$1" == -e ]] || exit 91\nshift\nexec "$@"\n')
        sshpass.chmod(0o755)
        inetcat = self.work / 'inetcat'
        inetcat.write_text('#!/bin/sh\nexit 0\n')
        inetcat.chmod(0o755)
        devices = self.work / 'idevice_id'
        devices.write_text('#!/bin/sh\nprintf "%s\\n" "$DEVICE_IDS"\n')
        devices.chmod(0o755)
        self.env = dict(os.environ, PATH=str(self.work)+':/usr/bin:/bin', CALL_LOG=str(self.log),
                        MonkeyDevDeviceIP='device-alias',MonkeyDevDevicePort='2222',
                        MonkeyDevDeviceUser='mobile',MonkeyDevDeviceKey=str(self.key),
                        MonkeyDevDevicePassword='',MonkeyDevDevicePasswordFile='',
                        MonkeyDevConnectionType='SSH',MonkeyDevAuthentication='AUTO',
                        MonkeyDevDeviceUDID='',
                        DEVICE_IDS='',TARGET_DEVICE_IDENTIFIER='',
                        MonkeyDevkillProcessOnInstall='bili-universal')

    def run_deploy(self):
        result=subprocess.run(['/bin/bash',str(ROOT/'Tools/tweak-deploy.sh'),str(self.package)],env=self.env,capture_output=True,text=True)
        calls=[json.loads(x) for x in self.log.read_text().splitlines()] if self.log.exists() else []
        return result,calls

    def test_key_upload_and_noninteractive_sudo(self):
        result,calls=self.run_deploy()
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertTrue(any(c['stdin']=='fixture deb' for c in calls))
        install=next(c for c in calls if 'dpkg -i' in c['args'][-1])
        self.assertIn('$(id -u)',install['args'][-1])
        self.assertIn('sudo -n',install['args'][-1])
        self.assertIn(str(self.key),install['args'])
        self.assertIn('device-alias',install['args'])
        self.assertNotIn('StrictHostKeyChecking=no',' '.join(install['args']))
        self.assertTrue(calls[-1]['args'][-1].startswith('rm -f '))

    def test_password_file_uses_stdin_not_command_arguments(self):
        secret='sample $ password; with spaces'
        password=self.work/'password'
        password.write_text(secret+'\n')
        self.env['MonkeyDevDevicePasswordFile']=str(password)
        result,calls=self.run_deploy()
        self.assertEqual(result.returncode,0,result.stderr)
        install=next(c for c in calls if 'dpkg -i' in c['args'][-1])
        self.assertEqual(install['stdin'],secret+'\n')
        self.assertTrue(install['secret_env'])
        self.assertNotIn(secret,result.stdout+result.stderr+json.dumps([c['args'] for c in calls]))

    def test_ssh_config_alias_does_not_require_project_user_or_key(self):
        self.env['MonkeyDevDeviceUser']=''
        self.env['MonkeyDevDeviceKey']=''
        self.env['MonkeyDevDeviceIP']='monkeydev-usb'
        result,calls=self.run_deploy()
        self.assertEqual(result.returncode,0,result.stderr)
        for call in calls:
            self.assertIn('monkeydev-usb',call['args'])
            self.assertNotIn('-i',call['args'])
            self.assertNotIn('-l',call['args'])
            self.assertNotIn('-F',call['args'])

    def test_install_failure_cleans_upload_and_does_not_restart(self):
        self.env['INSTALL_STATUS']='1'
        result,calls=self.run_deploy()
        self.assertNotEqual(result.returncode,0)
        self.assertFalse(any('killall' in c['args'][-1] for c in calls))
        self.assertTrue(calls[-1]['args'][-1].startswith('rm -f '))

    def test_invalid_process_rejected_before_connecting(self):
        self.env['MonkeyDevkillProcessOnInstall']='bad; command'
        result,calls=self.run_deploy()
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(calls,[])

    def test_usb_ip_and_key_password_combinations(self):
        for connection in ('USB','IP'):
            for auth in ('KEY','PASSWORD'):
                with self.subTest(connection=connection,auth=auth):
                    self.log.unlink(missing_ok=True)
                    self.env.update(MonkeyDevConnectionType=connection,
                                    MonkeyDevAuthentication=auth,
                                    MonkeyDevDeviceUDID='test-device-123',
                                    MonkeyDevDevicePassword='fixture password')
                    result,calls=self.run_deploy()
                    self.assertEqual(result.returncode,0,result.stderr)
                    args=calls[0]['args']
                    if connection=='USB':
                        self.assertTrue(any(x.startswith('ProxyCommand=') and 'inetcat' in x and '-u' in x for x in args))
                        self.assertIn('HostKeyAlias=monkeydev-usb-test-device-123',args)
                    else:
                        self.assertIn('ProxyCommand=none',args)
                    if auth=='KEY':
                        self.assertIn('BatchMode=yes',args)
                        self.assertFalse(calls[0]['secret_env'])
                    else:
                        self.assertIn('PubkeyAuthentication=no',args)
                        self.assertTrue(calls[0]['secret_env'])

    def test_ssh_alias_inherits_port_when_unset(self):
        self.env['MonkeyDevDevicePort']=''
        result,calls=self.run_deploy()
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertNotIn('-p',calls[0]['args'])

    def test_usb_multiple_devices_require_selection(self):
        self.env['MonkeyDevConnectionType']='USB'
        self.env['DEVICE_IDS']='first-device\nsecond-device'
        result,calls=self.run_deploy()
        self.assertNotEqual(result.returncode,0)
        self.assertIn('UDID',result.stderr)
        self.assertEqual(calls,[])

    def test_usb_detects_single_connected_device(self):
        self.env.update(MonkeyDevConnectionType='USB',DEVICE_IDS='test-device-123')
        result,calls=self.run_deploy()
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('HostKeyAlias=monkeydev-usb-test-device-123',calls[0]['args'])

    def test_usb_prefers_xcode_selected_device(self):
        udid='0123456789abcdef0123456789abcdef01234567'
        self.env.update(MonkeyDevConnectionType='USB',DEVICE_IDS='first\nsecond',TARGET_DEVICE_IDENTIFIER=udid)
        result,calls=self.run_deploy()
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('HostKeyAlias=monkeydev-usb-'+udid,calls[0]['args'])

    def test_project_relative_key_and_home_relative_password_file(self):
        password=self.work/'device.password'
        password.write_text('fixture password\n')
        self.env.update(HOME=str(self.work),PROJECT_DIR=str(self.work),
                        MonkeyDevDeviceKey='a key',
                        MonkeyDevDevicePasswordFile='~/device.password')
        result,calls=self.run_deploy()
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn(str(self.key),calls[0]['args'])
        install=next(c for c in calls if 'dpkg -i' in c['args'][-1])
        self.assertEqual(install['stdin'],'fixture password\n')
