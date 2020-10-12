import os
import sys
import subprocess
import re
import datetime

from helpers import util
from helpers import config
from helpers.log import Logger

class MySQL_Backup:
	name = "MySQL"
	type = "mysql"

	def __init__(self):
		self.logger = Logger()

	def add(self):
		# Read alias
		alias = input('Alias: ')

		# Check if alias exists
		while config.exists(alias):
			print("This alias already exists")
			alias = input('Alias: ')

		backup_path = input('Backup path (optional): ') or 'backups/' + alias
		db_name = input("Database name: ")
		db_user = input("Database user: ")
		db_host = input("Database host: ")
		db_pass = input("Database password: ")

		config.set(alias, 'type', 'database')
		config.set(alias, 'backup_path', backup_path)
		config.set(alias, 'db_name', db_name)
		config.set(alias, 'db_user', db_user)
		config.set(alias, 'db_host', db_host)
		config.set(alias, 'db_pass', db_pass)

		print("Added.")

	def get_timestring(self):
		"""
		Get current timestamp formatted as string

		@return string
		"""
		return datetime.datetime.now().strftime('%Y-%m-%d-%H%M%S')

	def backup(self, alias):
		"""
		Main worker

		@param string alias
		"""
		self.logger.write('### Backup {} (Database) ###'.format(alias))

		if not config.exists(alias):
			self.logger.write("Alias {} does not exist".format(alias))
			return

		filename = self.get_timestring()

		backup_path = config.get(alias, 'backup_path')
		db_name = config.get(alias, 'db_name')
		db_user = config.get(alias, 'db_user')
		db_host = config.get(alias, 'db_host')
		db_pass = config.get(alias, 'db_pass')

		# Make sure backup path exists
		util.create_backup_path(backup_path, alias)

		# Download database
		self.download(db_name, db_host, db_user, db_pass, backup_path, filename)

	def download(self, db_name, db_host, db_user, db_pass, path_to, filename):
		# Sanitize password
		db_pass = re.escape(db_pass)

		# Dump MySQL
		cmd = "mysqldump {} --add-drop-table -h {} -u {} -p{} > {}/{}.sql".format(db_name, db_host, db_user, db_pass, path_to, filename)
		subprocess.run([cmd], shell=True)