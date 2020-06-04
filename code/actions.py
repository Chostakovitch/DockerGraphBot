#!/usr/bin/env python
# coding=utf-8

import webdav.client as wc
import os
import paramiko
import sys

from webdav.client import WebDavException
from typing import List


class WebDAVUploader:
    '''
    This class performs upload to a WebDAV compatible server.
    '''
    def __init__(self,
                 hostname: str,
                 login: str,
                 password: str,
                 remote_path: str):
        '''
        Build an instance with credentials
        :param hostname : WebDAV link
        :param login : username
        :param password : password of the user
        :param remote_path : remote path where to store the files
        '''
        options = {
            'webdav_hostname': hostname,
            'webdav_login': login,
            'webdav_password': password,
        }
        self.__remote_path = remote_path
        self.__client = wc.Client(options)

    '''
    Upload files to the WebDAV server
    :param files: Paths to the files to upload
    '''
    def upload(self, files: List[str]):
        # Create remote folder if it does not exists
        if not self.__client.check(self.__remote_path):
            self.__client.mkdir(self.__remote_path)

        for file in files:
            filename = os.path.basename(file)
            try:
                self.__client.upload_sync(
                    remote_path='{}/{}'.format(self.__remote_path, filename),
                    local_path=file)
                print("File {} successfully uploaded!".format(filename))
            except WebDavException as e:
                print("Error uploading file {0} : {1}".format(f, e), file=sys.stderr)


class SFTPUploader:
    '''
    This class performs uploads to a SFTP server.
    Currently only connection via user/password is supported.
    '''
    def __init__(self,
                 hostname: str,
                 port: int,
                 login: str,
                 password: str,
                 base_path: str = ''):
        '''
        Build an instance with credentials
        :param hostname public URL
        :param port:       SFTP port
        :param login:      username
        :param password:   cleartext password
        :param base_path:  directory for uploads
        '''
        self.__dir = base_path

        transport = paramiko.Transport((hostname, port))
        transport.connect(None, login, password)
        try:
            self.__client = paramiko.SFTPClient.from_transport(transport)
        except Exception as e:
            print("Error creating SFTP client : {}".format(e))

        # Create the directory if it does not exists
        try:
            self.__client.listdir(base_path)
            print("Folder already existing, skipping creation...")
        except FileNotFoundError:
            self.__client.mkdir(base_path)

    '''
    Upload files to the STFP server
    :param files: Paths of files to upload
    '''
    def upload(self, files: List[str]):
        for f in files:
            filename = os.path.basename(f)
            try:
                self.__client.put(f, '{}/{}'.format(self.__dir, filename))
                print("File {} successfully uploaded!".format(filename))
            except Exception as e:
                print('Error uploading file {0} : {1}'.format(f, e), file=sys.stderr)

    def __del__(self):
        self.__client.close()
