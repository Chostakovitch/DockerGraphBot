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
        logging.info('Starting upload of {}'.format(files))
        # Create remote folder if it does not exists
        if not self.__client.check(self.__remote_path):
            self.__client.mkdir(self.__remote_path)

        for file in files:
            filename = os.path.basename(file)
            try:
                self.__client.upload_sync(
                    remote_path='{}/{}'.format(self.__remote_path, filename),
                    local_path=file)
                logging.info("File {} successfully uploaded!".format(filename))
            except WebDavException as e:
                logging.error('Error uploading file {}'.format(file))
                logging.exception(e)
        logging.info('Finished upload')


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
            logging.error("Error creating SFTP client for {}".format(hostname))
            logging.exception(e)

        # Create the directory if it does not exists
        try:
            self.__client.listdir(base_path)
            info = "Folder {} already existing on {}, skipping creation..."
            logging.info(info.format(
                hostname,
                base_path
            ))
        except FileNotFoundError:
            self.__client.mkdir(base_path)

    '''
    Upload files to the STFP server
    :param files: Paths of files to upload
    '''
    def upload(self, files: List[str]):
        logging.info('Starting upload of {}'.format(files))
        for file in files:
            filename = os.path.basename(file)
            try:
                self.__client.put(file, '{}/{}'.format(self.__dir, filename))
                logging.info("File {} successfully uploaded!".format(filename))
            except Exception as e:
                logging.error('Error uploading file {}'.format(file))
                logging.exception(e)
        logging.info('Finished upload')

    def __del__(self):
        self.__client.close()
