import json
import os
from enum import Enum
from getpass import getpass
import oracledb


# enum for credential types
class CredentialType(Enum):
    USERINPUT = 1
    FILE = 2
    ENVIRONMENT = 3


# helper class to get/store credentials
class CredentialsHelper:
    credentials_file = "credentials.json"
##
    # python does not support method overloading, so we provide default values for the optional parameters
    # background: python stores method definitions in a dictionary, so we can't have two methods with the same name
    def __init__(self, cred_type: CredentialType = None):
        self.username = None
        self.password = None
        self.host = None
        self.port = None
        self.sid = None
        self.dsn = None
        self.cred_type = cred_type

        if cred_type is None:
            # try getting credentials from environment variables first
            self._get_from_environment()
            # check if username, password and dsn are set
            if self.username is None or self.password is None or self.dsn is None:
                print("Credentials not found in environment variables. -> trying file")
                # if not, try getting credentials from file
                self._get_from_file()
                # check if username, password and dsn are set
                if self.username is None or self.password is None or self.dsn is None:
                    print("Credentials not found in file. -> trying user input")
                    # if not, get credentials from user input
                    self._get_user_input()
        else:
            # load credentials based on cred_type using lambda functions
            # this a python alternative to switch/case
            self.cred_type_dict = {
                CredentialType.USERINPUT: self._get_user_input,
                CredentialType.FILE: self._get_from_file,
                CredentialType.ENVIRONMENT: self._get_from_environment
            }
            # call the function based on the cred_type
            self.cred_type_dict[self.cred_type]()

    # read credentials from user input
    def _get_user_input(self):
        self.username = input("Enter username: ")
        # we can use getpass to read the password from the console without echoing it
        # but only if we run the script from the console, not from the IDE
        self.password = getpass("Enter password: ")
        self.host = input("Enter host: ")
        self.port = input("Enter port: ")
        self.sid = input("Enter SID: ")
        self.dsn = oracledb.makedsn(host=self.host, port=self.port, sid=self.sid)

    # load credentials from file
    def _get_from_file(self):
        try:
            f = open(self.credentials_file, 'rt')
            credentials_json = json.loads(f.read())
            self.username = credentials_json['username']
            self.password = credentials_json['password']
            self.dsn = credentials_json['dsn']
            f.close()
        except FileNotFoundError:
            print("File not found: " + self.credentials_file)

    # load credentials from environment variables
    def _get_from_environment(self):
        self.username = os.environ.get('USERNAME')
        self.password = os.environ.get('PASSWORD')
        self.dsn = os.environ.get('DSN')

    def get_username(self):
        return self.username

    def get_password(self):
        return self.password

    def get_dsn(self):
        return self.dsn
