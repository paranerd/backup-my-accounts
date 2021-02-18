"""Backup strategy for remote servers using SSH."""

import os
import subprocess
import re
import shutil

from helpers import util
from helpers.strategy import Strategy

class Server(Strategy):
    """Backup strategy for remote servers using SSH."""
    NAME = 'Server'
    TYPE = 'server'

    def start_backup(self):
        """
        Start backup.
        """
        if self.config.get('archive'):
            self.archive(self.config.get('ssh_host'), self.config.get('ssh_user'), self.config.get('ssh_pass'), self.config.get('path'), self.backup_path, self.config.get('exclude'), self.config.get('zip_on_server'))
        else:
            self.sync(self.config.get('ssh_host'), self.config.get('ssh_user'), self.config.get('ssh_pass'), self.config.get('path'), self.config.get('exclude'))

    def sync(self, host, user, password, path_from, exclude=[]):
        """
        Sync files using rsync.

        @param string host
        @param string user
        @param string password
        @param string path_from
        @param list exclude
        """
        # Escape password
        password = re.escape(password)
        exclude_str = ' '.join(list(map(lambda x: "--exclude '" + x + "'", exclude)))

        # Sync using rsync
        cmd = "sshpass -p {} rsync -a {} -e 'ssh -o StrictHostKeyChecking=no' {}@{}:{} {}/".format(password, exclude_str, user, host, path_from, self.backup_path)
        subprocess.run([cmd], shell=True)

    def archive(self, host, user, password, path_from, path_to, exclude=[], zip_on_server=False):
        """
        Download files to tmp using rsync and creates a zip archive from it.

        @param string host
        @param string user
        @param string password
        @param string path_from
        @param string path_to
        @param list exclude
        """
        # Escape password
        password = re.escape(password)
        exclude_str = ' '.join(list(map(lambda x: "--exclude '" + x + "'", exclude)))

        # Determine filename
        filename = self.alias + '_' + util.startup_time

        if zip_on_server:
            try:
                # Create zip on remote server
                cmd = "sshpass -p {} ssh {}@{} -o StrictHostKeyChecking=no \"cd {}/.. && zip -r {}/{}.zip `basename {}` {}\"".format(password, user, host, path_from, path_from, filename, path_from, exclude_str)
                subprocess.run([cmd], shell=True, check=True, capture_output=True)
            except subprocess.CalledProcessError as err:
                self.logger.error('Error zipping: {} STDOUT: {})'.format(err.stderr.decode('utf-8'), err.stdout.decode('utf-8')))

            try:
                # Pull backups
                cmd = "sshpass -p {} rsync --remove-source-files -a -e ssh {}@{}:{}/{}.zip {}/".format(password, user, host, path_from, filename, path_to)
                subprocess.run([cmd], shell=True, check=True, capture_output=True)
            except subprocess.CalledProcessError as err:
                self.logger.error('Error pulling backups: {} STDOUT: {})'.format(err.stderr.decode('utf-8'), err.stdout.decode('utf-8')))
        else:
            # Create temporary folder
            tmp_path = util.create_tmp_folder()

            try:
                cmd = 'sshpass -p {} rsync -a {} -e ssh {}@{}:{}/ {}'.format(password, exclude_str, user, host, path_from, tmp_path)
                print(cmd)
                subprocess.run([cmd], shell=True, check=True, capture_output=True)
            except subprocess.CalledProcessError as err:
                self.logger.error('Error pulling backups: {} STDOUT: {})'.format(err.stderr.decode('utf-8'), err.stdout.decode('utf-8')))

            # Create archive from tmp
            destination = os.path.join(path_to, filename)
            shutil.make_archive(destination, 'zip', tmp_path)
