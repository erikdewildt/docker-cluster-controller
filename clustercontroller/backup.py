"""Rotating backup functionality."""
import glob
import os
import subprocess
from datetime import datetime
from pathlib import Path
from shutil import copyfile, move

from clustercontroller.clustercontroller import create_logger


class Backup:
    """Backup."""

    logger = None
    name = None
    command = None

    destination_folder = None
    hourly_folder = 'hourly'
    daily_folder = 'daily'
    weekly_folder = 'weekly'
    monthly_folder = 'monthly'

    hours_to_keep = 24
    days_to_keep = 7
    weeks_to_keep = 4
    months_to_keep = 12

    now = datetime.now()

    def __init__(self):
        """Initialise the Backup class."""
        self.logger = create_logger(name='backup')
        self.parse_settings()
        timestamp = self.now.strftime('%Y-%m-%d %H:%M:%S')
        self.logger.info(f'Backup started at: {timestamp}')

        if not self.destination_folder:
            self.logger.error('Destination folder is not set. Please check settings.')

        self.create_destination_folder(destination_folder=f'{self.destination_folder}')

    def run(self, name=None, command=None):

        if not name:
            self.logger.error('Name not specified.')
        else:
            self.name = name

        if not command:
            self.logger.error('Backup command is not specified.')
        else:
            self.command = command

        if self.name and self.command and self.destination_folder:
            self.create_backup()

    def parse_settings(self):
        """Parse environment settings."""
        try:
            self.hours_to_keep = int(os.environ.get('BACKUP_HOURS_TO_KEEP'))
            self.days_to_keep = int(os.environ.get('BACKUP_DAYS_TO_KEEP'))
            self.weeks_to_keep = int(os.environ.get('BACKUP_WEEKS_TO_KEEP'))
            self.months_to_keep = int(os.environ.get('BACKUP_MONTHS_TO_KEEP'))
            self.destination_folder = os.environ.get('BACKUP_DESTINATION_FOLDER')
        except AttributeError:
            self.logger.error(f'Error, please verify that all settings have been correctly set.')

    #
    # Helper methods
    #
    def create_destination_folder(self, destination_folder=None):
        """Check if backup destination exists and create it if not."""
        if not os.path.exists(destination_folder):
            Path(f'{destination_folder}').mkdir(parents=True, exist_ok=True)
            self.logger.info(f'Destination folder `{destination_folder}` did not exist and has been created.')
        else:
            self.logger.info(f'Using existing destination folder: `{destination_folder}`')

    @staticmethod
    def list_files_ordered_by_timestamp(destination=None):
        """Return a list of files ordered by create timestamp."""
        files = glob.glob(f'{destination}/*.*')
        files.sort(key=os.path.getmtime)  # Sort by create time
        return files

    def get_latest_file(self, destination=None):
        latest_file = None
        try:
            latest_file = self.list_files_ordered_by_timestamp(destination=destination)[-1:][0]
        except IndexError:
            self.logger.info('No backup file found.')
        return latest_file

    def delete_old_files(self, destination=None, number_to_keep=1):
        """Delete all old files which are extending the set retention."""
        files = self.list_files_ordered_by_timestamp(destination=destination)
        for file in files[:-number_to_keep]:
            os.remove(file)
            self.logger.info(f'Removed: {file}')

    def file_exists(self, destination=None, name=None, pattern=None, extension=None):
        """Check if a file exists."""
        if os.path.isfile(f'{destination}/{name}_{pattern}.{extension}'):
            self.logger.info(f'File {destination}/{name}_{pattern}.{extension} already exists, skipping...')
            return True
        return False

    def copy_backup(self, destination=None, name=None, pattern=None, extension=None, source=None):
        """Copy a file."""
        self.create_destination_folder(destination_folder=destination)
        target = f'{destination}/{name}_{pattern}.{extension}'
        copyfile(source, target)
        self.logger.info(f'Created copy of `{source}` to `{target}`')

    #
    # Create backup
    #
    def create_backup(self):
        """Do the actual backup."""

        # Rotate old backup files
        latest_file = self.get_latest_file(destination=f'{self.destination_folder}')

        if 'latest' in str(latest_file):
            self.archive(backup_file=latest_file)
            os.remove(latest_file)

        # Start the new backup
        self.logger.info(subprocess.run(self.command, stdout=subprocess.PIPE).stdout.decode('utf-8'))

        # Rename the latest file in the destination folder to 'latest' while preserving the extension.
        latest_file = self.get_latest_file(destination=f'{self.destination_folder}')

        if latest_file and 'latest' not in str(latest_file):
            extension = latest_file.split('.', 1)[1]
            move(f'{latest_file}', f'{self.destination_folder}/latest.{extension}')

        # Finish backup
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.logger.info(f'Backup finished at: {timestamp}')

    #
    # Main Rotating logic
    #
    def archive(self, backup_file=None):
        """Archive the files with respect to retention settings."""
        schema = {
            'hourly': {
                'pattern': self.now.strftime('%Y-%m-%d_%H'),
                'destination': f'{self.destination_folder}/{self.hourly_folder}',
                'retention': self.hours_to_keep
            },
            'daily': {
                'pattern': self.now.strftime('%Y-%m-%d'),
                'destination': f'{self.destination_folder}/{self.daily_folder}',
                'retention': self.days_to_keep
            },
            'weekly': {
                'pattern': self.now.strftime('%Y-%V'),
                'destination': f'{self.destination_folder}/{self.weekly_folder}',
                'retention': self.weeks_to_keep
            },
            'monthly': {
                'pattern': self.now.strftime('%Y-%b'),
                'destination': f'{self.destination_folder}/{self.monthly_folder}',
                'retention': self.months_to_keep
            }
        }

        extension = backup_file.split('.', 1)[1]

        for key, value in schema.items():
            self.logger.info(f'Running rotation scheme `{key}` for `{self.name}`')
            if not self.file_exists(destination=value['destination'], name=self.name, pattern=value['pattern'],
                                    extension=extension):
                self.copy_backup(destination=value['destination'], name=self.name, pattern=value['pattern'],
                                 extension=extension, source=backup_file)
                self.delete_old_files(destination=value['destination'], number_to_keep=value['retention'])


backup = Backup()


def run_backup(name=None, command=None):
    backup.run(name=name, command=command)
