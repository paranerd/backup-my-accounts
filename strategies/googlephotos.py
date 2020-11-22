import os
import re
import json
from urllib.parse import quote_plus
import webbrowser
import requests
import urllib3

# Prevent SSL certificate errors
from urllib3.contrib import pyopenssl
pyopenssl.extract_from_urllib3()

from helpers import util
from helpers import config
from helpers.cache import Cache
from helpers.log import Logger

class GooglePhotos():
    NAME = "Google Photos"
    TYPE = "googlephotos"
    API_URL = "https://photoslibrary.googleapis.com/v1"
    credentials = ''
    token = ''
    backup_path = ''
    excluded = []
    alias = ''
    cache = None

    def __init__(self):
        """
        Constructor
        """
        self.logger = Logger()
        self.cache = Cache(self.alias)

    def add(self):
        """
        Add Google Photos account
        """
        # Read alias
        self.alias = input('Alias: ')

        # Check if alias exists
        while config.exists(self.alias):
            print("This alias already exists")
            self.alias = input('Alias: ')

        # Show instructions
        self.show_instructions()

        credentials_str = input('Paste content of credentials file: ')
        self.credentials = json.loads(credentials_str)['installed']

        code = self.request_code()
        token = self.request_token(code)

        # Read backup path
        backup_path = input('Backup path (optional): ') or 'backups/' + self.alias

        # Write config
        config.set(self.alias, 'type', self.TYPE)
        config.set(self.alias, 'credentials', self.credentials)
        config.set(self.alias, 'token', token)
        config.set(self.alias, 'backup_path', backup_path)

        print("Added.")

    def backup(self, alias):
        self.logger.set_source(alias)
        self.logger.info("Starting...")

        if not config.exists(alias):
            self.logger.error("Alias {} does not exist".format(alias))
            return

        self.alias = alias
        self.credentials = config.get(alias, 'credentials', None)
        self.token = config.get(alias, 'token')
        self.backup_path = config.get(alias, 'backup_path')
        self.excluded = config.get(alias, 'exclude') or []

        # Make sure backup path exists
        util.create_backup_path(self.backup_path, alias)

        try:
            self.logger.info("Getting albums...")
            albums = self.get_albums()

            for album in albums:
                if not self.check_if_excluded(album['title']):
                    self.get_album_content(album['id'], album['title'])

            # Done
            self.logger.info("Done")
        except KeyboardInterrupt:
            self.logger.warn("Interrupted")
        except Exception as e:
            self.logger.error(e)
        finally:
            return {
                'errors': self.logger.count_errors(),
                'warnings': self.logger.count_warnings()
            }

    def show_instructions(self):
        print()
        print('If you already have an OAuth-Client-ID, download the JSON')
        print('Otherwise, here\'s how to get credentials:')
        print('1. Go to https://console.developers.google.com/')
        print('2. Choose or create a project')
        print('3. Activate Photos API here: https://console.developers.google.com/apis/library/photoslibrary.googleapis.com')
        print('4. Open https://console.developers.google.com/apis/credentials/consent')
        print('5. Choose "External"')
        print('6. Enter a name and click "Save"')
        print('7. Open https://console.developers.google.com/apis/credentials')
        print('8. Click on "Create Credentials" -> OAuth-Client-ID -> Desktop Application')
        print('9. Ignore the pop-up')
        print('10. Download the client ID JSON')
        print()

    def build_auth_uri(self):
        auth_uri = self.credentials['auth_uri']
        auth_uri += "?response_type=code"
        auth_uri += "&redirect_uri=" + quote_plus(self.credentials['redirect_uris'][0])
        auth_uri += "&client_id=" + quote_plus(self.credentials['client_id'])
        auth_uri += "&scope=https://www.googleapis.com/auth/photoslibrary"
        auth_uri += "&access_type=offline"
        auth_uri += "&approval_prompt=auto"

        return auth_uri

    def request_code(self):
        # Build auth uri
        auth_uri = self.build_auth_uri()

        # Try opening in browser
        webbrowser.open(auth_uri, new=2)

        print()
        print("If your browser does not open, go to this website:")
        print(auth_uri)
        print()

        # Return code
        return input('Enter code: ')

    def execute_request(self, url, headers={}, params={}, method="GET", retry=False):
        if "access_token" in self.token:
            # Set Authorization-Header
            auth_header = {
                'Authorization': 'Bearer {}'.format(self.token['access_token'])
            }
            headers.update(auth_header)

        # Execute request
        if method == 'GET':
            res = requests.get(url, headers=headers, params=params)
        elif method == 'POST':
            res = requests.post(url, headers=headers, data=params)
        elif method == 'HEAD':
            res = requests.head(url, headers=headers)

        if res.status_code == 401:
            # Token expired
            if not retry:
                self.token = self.request_token()
                return self.execute_request(url, headers, params, method, True)
            else:
                raise Exception("Failed to refresh token")

        body = res.json() if method != 'HEAD' else None

        return {'status': res.status_code, 'headers': res.headers, 'body': body}

    def check_if_excluded(self, name):
        for e in self.excluded:
            if re.match(e, name):
                return True

        return False

    def get_albums(self, pageToken=""):
        params = {
            "pageSize": "50",
        }

        if pageToken:
            params['pageToken'] = pageToken

        res = self.execute_request(self.API_URL + "/albums", {}, params)

        albums = res['body']['albums']

        if 'nextPageToken' in res['body']:
            albums.extend(self.get_albums(res['body']['nextPageToken']))

        return albums

    def get_album_content(self, album_id, name, pageToken=""):
        params = {
            "pageSize": "100",
            "albumId": album_id
        }

        if pageToken:
            params['pageToken'] = pageToken

        res = self.execute_request(self.API_URL + "/mediaItems:search", {}, params, "POST")

        if 'mediaItems' in res['body']:
            items = res['body']['mediaItems']

            result = re.match('([0-9]{4})-', name)

            year = result.group(1) if result else '0000'

            for item in items:
                path = self.backup_path + "/" + year + "/" + name
                filename = self.cache.get(item['id'])
                url_postfix = "=dv" if 'video' in item['mediaMetadata'] else "=w" + item['mediaMetadata']['width'] + "-h" + item['mediaMetadata']['height']

                if 'video' in item['mediaMetadata']:
                    filename = filename if filename else self.get_video_filename(item)

                self.download(item['baseUrl'] + url_postfix, item['id'], path, filename)

        if 'nextPageToken' in res['body']:
            self.get_album_content(album_id, name, res['body']['nextPageToken'])

    def get_video_filename(self, item):
        res = self.execute_request(item['baseUrl'], {}, {}, "HEAD")

        filename = re.search('"(.*?)"', res['headers']['Content-Disposition']).group(1)
        filename, _ = os.path.splitext(filename)

        return filename + ".mp4"

    def download(self, url, item_id, path, filename=""):
        # Create folder if not exists
        if not os.path.exists(path):
            os.makedirs(path)

        headers = {
            'Authorization': 'Bearer {}'.format(self.token['access_token'])
        }

        # Check if file already exists
        if filename:
            if os.path.isfile(os.path.join(path, filename)):
                return
        else:
            res = self.execute_request(url, {}, {}, 'HEAD')

            if res['status'] != 200:
                self.logger.warn("Could not get file info ({}) -> {}".format(str(res['status']), str(res['headers'])))
                return

            filename = re.search('"(.*?)"', res['headers']['Content-Disposition']).group(1)

            if os.path.isfile(os.path.join(path, filename)):
                self.cache.set(item_id, filename)
                return

        # Download file
        http = urllib3.PoolManager()
        r = http.request('GET', url, headers=headers, preload_content=False)

        if r.status == 200:
            filename = filename if filename else re.search('"(.*?)"', r.headers['Content-Disposition']).group(1)
            self.cache.set(item_id, filename)
            self.logger.info(os.path.join(path, filename))

            with open(os.path.join(path, filename), 'wb') as out:
                while True:
                    data = r.read(128)
                    if not data:
                        break
                    out.write(data)

            r.release_conn()
        else:
            self.logger.error("Error downloading ({}) -> {}".format(str(r.status), str(r.data)))

    def create_album(self, name):
        params = {
            "album": {"title": name}
        }
        self.execute_request(self.API_URL + "/albums", {}, json.dumps(params), "POST")

    def request_token(self, code=""):
        if not self.credentials:
            raise Exception('Could not read credentials')

        if not code and not self.token:
            raise Exception('Could not read token')

        headers = {
            'Content-Type': 'application/x-www-form-urlencoded'
        }

        params = {
            'client_id' 	: self.credentials['client_id'],
            'client_secret'	: self.credentials['client_secret'],
            'redirect_uri'	: self.credentials['redirect_uris'][0],
        }

        if code:
            params['grant_type'] = 'authorization_code'
            params['code'] = code
        else:
            params['grant_type'] = 'refresh_token'
            params['refresh_token'] = self.token['refresh_token']

        res = self.execute_request(self.credentials['token_uri'], headers, params, "POST")

        if res['status'] == 200:
            if self.token:
                res['body']['refresh_token'] = self.token['refresh_token']

            config.set(self.alias, 'token', res['body'])
            return res['body']
        else:
            raise Exception("Error getting token: " + str(res['body']))