#!/usr/bin/env python
# coding=utf-8
"""Logic for performing actions on files after their generation."""
import os
import logging
from typing import List

import paramiko

import webdav.client as wc
from webdav.client import WebDavException


class WebDAVUploader:
    """This class performs upload to a WebDAV compatible server."""

    def __init__(self,
                 hostname: str,
                 login: str,
                 password: str,
                 remote_path: str):
        """
        Build an instance with credentials.

        :param hostname : WebDAV link
        :param login : username
        :param password : password of the user
        :param remote_path : remote path where to store the files
        """
        options = {
            'webdav_hostname': hostname,
            'webdav_login': login,
            'webdav_password': password,
        }
        self.__remote_path = remote_path
        self.__client = wc.Client(options)

    def upload(self, files: List[str]):
        """
        Upload files to the WebDAV server.

        :param files: Paths to the files to upload
        """
        logging.info('Starting upload of %s', files)
        # Create remote folder if it does not exists
        if not self.__client.check(self.__remote_path):
            self.__client.mkdir(self.__remote_path)

        for file in files:
            filename = os.path.basename(file)
            try:
                self.__client.upload_sync(
                    remote_path=f'{self.__remote_path}/{filename}',
                    local_path=file)
                logging.info("File %s successfully uploaded!", filename)
            except WebDavException as e:
                logging.error('Error uploading file %s', file)
                logging.exception(e)
        logging.info('Finished upload')


class SFTPUploader:
    """
    This class performs uploads to a SFTP server.

    Currently only connection via user/password is supported.
    """

    def __init__(self,
                 hostname: str,
                 port: int,
                 login: str,
                 password: str,
                 base_path: str = ''):
        """
        Build an instance with credentials.

        :param hostname public URL
        :param port:       SFTP port
        :param login:      username
        :param password:   cleartext password
        :param base_path:  directory for uploads
        """
        self.__dir = base_path

        transport = paramiko.Transport((hostname, port))
        try:
            transport.connect(None, login, password)
            self.__client = paramiko.SFTPClient.from_transport(transport)
        except paramiko.ssh_exception.SSHException as e:
            logging.error("Error creating SFTP client for %s", hostname)
            logging.exception(e)

        # Create the directory if it does not exists
        try:
            self.__client.listdir(base_path)
            info = "Folder %s already existing on %s, skipping creation..."
            logging.info(info, hostname, base_path)
        except FileNotFoundError:
            self.__client.mkdir(base_path)

    def upload(self, files: List[str]):
        """
        Upload files to the STFP server.

        :param files: Paths of files to upload
        """
        logging.info('Starting upload of %s', files)
        for file in files:
            filename = os.path.basename(file)
            try:
                self.__client.put(file, f'{self.__dir}/{filename}')
                logging.info("File %s successfully uploaded!", filename)
            except Exception as e:
                logging.error('Error uploading file %s', file)
                logging.exception(e)
        logging.info('Finished upload')

    def __del__(self):
        """Close the SSH connection."""
        self.__client.close()
