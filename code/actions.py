#!/usr/bin/env python
#coding=utf-8

import webdav.client as wc
import os

from webdav.client import WebDavException
from typing import List

'''
This class performs upload to a WebDAV compatible server.
'''
class WebDAVUploader:
    '''
    Build an instance with credentials
    :param hostname : WebDAV link
    :param login : username
    :param password : password of the user
    :param remote_path : remote path where to store the files
    '''
    def __init__(self, hostname: str, login: str, password: str, remote_path: str):
        options = {
            'webdav_hostname': hostname,
            'webdav_login': login,
            'webdav_password': password,
        }
        self.__remote_path = remote_path
        self.__client = wc.Client(options)

    '''
    Upload files to the WebDAV server
    :param files : Paths to the files to upload
    '''
    def upload(self, files: List[str]):
        if not self.__client.check(self.__remote_path):
            self.__client.mkdir(self.__remote_path)

        for f in files:
            filename = os.path.basename(f)
            try:
                self.__client.upload_sync(remote_path = '{}/{}'.format(self.__remote_path, filename), local_path = f)
                print("File {} successfully uploaded!".format(filename))
            except WebDavException as e:
                print("Error uploading file : {}".format(e))
