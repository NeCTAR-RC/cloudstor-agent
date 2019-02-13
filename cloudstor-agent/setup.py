#!/usr/bin/env python
from __future__ import print_function

import logging
import os
import pwd
import subprocess

import requests

from fstab import Fstab

logging.basicConfig(level=logging.DEBUG)
LOG = logging.getLogger(__name__)

# Dynamic Vendordata URL
VENDOR_DATA_URL = 'http://169.254.169.254/openstack/latest/vendor_data2.json'

# CloudStor config
CLOUDSTOR_URL = 'https://cloudstor.aarnet.edu.au/plus/remote.php/webdav/'
CLOUDSTOR_MOUNT = '/cloudstor'


def get_default_user():
    try:
        passwd = pwd.getpwuid(1000)
        return passwd.pw_name
    except KeyError:
        return os.listdir('/home')[0]


def is_mounted(path=CLOUDSTOR_MOUNT):
    return os.path.ismount(path)


def test_cloudstor_creds(username, password):
    LOG.info('Testing CloudStor credentials')
    try:
        r = requests.get(CLOUDSTOR_URL, timeout=10, auth=(username, password))
        r.raise_for_status()
    except requests.exceptions.HTTPError:
        if r.status_code in [401, 503]:
            LOG.error('There is an authentication issue with your CloudStor '
                      'credentials. Please contact support.')
        else:
            LOG.error('There was an unknown error when testing your CloudStor '
                      'credentials. The error was: %s', r.text)
        return False
    return True


def add_davfs2_secret(url, username, password):
    LOG.info('Adding credentials to davfs2 config')
    secrets_file = '/etc/davfs2/secrets'

    # davfs2 can barf at some special chars in the password, so we just need
    # to double-quote the whole password, then escape any of those quotes if
    # they're in the password
    quote_pass = password.replace('"', r'\"')

    with open(secrets_file, 'r+') as f:
        lines = f.readlines()
        f.seek(0)
        f.writelines(l for l in lines if not l.startswith(url))
        f.truncate()

    with open(secrets_file, 'a') as f:
        f.write('{} {} "{}"\n'.format(url, username, quote_pass))


def add_fstab_entry():
    fstab = Fstab()
    fstab.read()

    if not fstab.get_entry(CLOUDSTOR_MOUNT):
        LOG.info("Adding fstab entry")

        options = '_netdev'
        default_user = get_default_user()
        if default_user:
            options = 'uid={},_netdev'.format(default_user)

        fstab.add_entry(CLOUDSTOR_URL, CLOUDSTOR_MOUNT, 'davfs',
                        options, 0, 0)
        fstab.write()
    return True


def mount(mount_path):
    LOG.info('Mounting CloudStor to %s', CLOUDSTOR_MOUNT)
    try:
        subprocess.check_output(['/bin/mount', CLOUDSTOR_MOUNT],
                                stderr=subprocess.STDOUT)
        return True
    except subprocess.CalledProcessError as e:
        LOG.error(e.output.decode())
    return False


def cloudstor_setup(username, password):
    """CloudStor setup

    If credentials exist, we test that they're valid, then setup the fstab
    and mount for it.
    """
    LOG.info("Setting up CloudStor for account: %s", username)

    if is_mounted():
        LOG.info("CloudStor already mounted.")
        return True

    if not test_cloudstor_creds(username, password):
        LOG.info("CloudStor login failure.")
        return False

    add_fstab_entry()

    if not os.path.exists(CLOUDSTOR_MOUNT):
        LOG.info('Creating mountpoint: %s', CLOUDSTOR_MOUNT)
        os.mkdir(CLOUDSTOR_MOUNT)

    add_davfs2_secret(CLOUDSTOR_URL, username, password)

    mount(CLOUDSTOR_MOUNT)
    return True


def main():
    LOG.info("Fetching data from: %s", VENDOR_DATA_URL)
    resp = requests.get(VENDOR_DATA_URL)

    vendor_data = resp.json()

    nectar_data = vendor_data.get('nectar')
    if nectar_data:
        cloudstor_data = nectar_data.get('cloudstor')
        if 'username' and 'password' in cloudstor_data:
            cloudstor_setup(**cloudstor_data)


if __name__ == '__main__':
    main()
