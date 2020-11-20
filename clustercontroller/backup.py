"""Rotating backup functionality."""

import glob
import os
import re
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

    # By default, a fresh backup file that doesn't contain "latest" is
    # renamed to "latest" but with file name extensions preserved. (If
    # "latest" files are produced by the backup command they don't
    # need this default renaming.)
    default_backup_rename = (r"^(?!.*latest)[^.]*(?P<exts>.*)$", r"latest\g<exts>")

    # By default, rename a (latest) backup file to an archive file by
    # replacing "latest" with "backup" plus a placeholder ARCHIVELABEL
    # string, which is replaced by a time indication by the archive
    # routine. Information before and after "latest", including
    # extensions are preserved.

    ARCHIVELABEL = "ARCHIVELABEL"
    default_archive_rename = (r"latest", rf"backup_{ARCHIVELABEL}")

    now = datetime.now()

    def __init__(self):
        """Initialise the Backup class."""
        self.logger = create_logger(name='backup')
        self.parse_settings()

        if not self.destination_folder:
            self.logger.error('Destination folder is not set. Please check settings.')

        self.create_destination_folder(destination_folder=f'{self.destination_folder}')

    def run(self, name=None, command=None, backup_rename=default_backup_rename, archive_rename=default_archive_rename):
        """
        Run backup and archiving process.

        Parameter backup_rename, if non-empty (evaluates to boolean True),
        specifies renaming of the backup file in the format of a tuple
        of a regular expression pattern for the file name and a
        replacement string, as used in re.sub(), so that groups
        captured in the pattern match can be used in the new name.

        Parameter archive_rename is similar, for making archive file names
        out of backup files. The first component is also used as a
        regular expression pattern for re.search to select files that
        should be archived according to the schema in the archive()
        method.  The archive replacement string can include a string
        self.ARCHIVELABEL which is replaced during archiving,
        typically by a time indication for the rotation period (e.g.,
        date and hour).
        """

        if not name:
            self.logger.error('Name not specified.')
        else:
            self.name = name

        if not command:
            self.logger.error('Backup command is not specified.')
        else:
            self.command = command

        if self.name and self.command and self.destination_folder:
            self.create_backup(backup_rename=backup_rename, archive_rename=archive_rename)

    def parse_settings(self):
        """Parse environment settings."""
        try:
            self.hours_to_keep = int(os.environ.get('BACKUP_HOURS_TO_KEEP'))
            self.days_to_keep = int(os.environ.get('BACKUP_DAYS_TO_KEEP'))
            self.weeks_to_keep = int(os.environ.get('BACKUP_WEEKS_TO_KEEP'))
            self.months_to_keep = int(os.environ.get('BACKUP_MONTHS_TO_KEEP'))
            self.destination_folder = os.environ.get('BACKUP_DESTINATION_FOLDER')
        except (AttributeError, TypeError):
            self.logger.error('Error, please verify that all settings have been correctly set.')

    #
    # Helper methods
    #
    def create_destination_folder(self, destination_folder=None):
        """Check if destination folder exists and create it if not."""
        if not destination_folder:
            self.logger.info('Unable to create undefined destination folder.')
            return

        if not os.path.exists(destination_folder):
            Path(f'{destination_folder}').mkdir(parents=True, exist_ok=True)
            self.logger.info(f'Destination folder `{destination_folder}` did not exist and has been created.')
        else:
            self.logger.info(f'Using existing destination folder: `{destination_folder}`')

    @staticmethod
    def list_files_ordered_by_timestamp(destination=".", regexp=None):
        """Return a list of (re.search matching) files ordered by create timestamp."""
        files = glob.glob(f'{destination}/*.*')
        if regexp:
            files = [path for path in files if re.search(regexp, os.path.basename(path))]
        files.sort(key=os.path.getmtime)  # Sort by create time
        return files

    def get_latest_file(self, destination=".", regexp=None):
        """Get latest (matching) file at destination."""
        files = self.list_files_ordered_by_timestamp(destination=destination, regexp=regexp)
        if files:
            return files[-1]
        return None

    def delete_old_files(self, destination=None, number_to_keep=1):
        """Delete all old files which are extending the set retention."""
        files = self.list_files_ordered_by_timestamp(destination=destination)
        for file in files[:-number_to_keep]:
            os.remove(file)
            self.logger.info(f'Removed: {file}')

    def archive_name(self, backup_file, archive_rename, archivelabel):
        """Create name of archive file using renaming and labeling patterns."""
        name = os.path.basename(backup_file)
        if archive_rename:
            (re_pattern, re_replacement) = archive_rename
            name = re.sub(re_pattern, re_replacement, name)
        if archivelabel:
            if self.ARCHIVELABEL in name:
                name = name.replace(self.ARCHIVELABEL, archivelabel)
            else:
                # Append archive label before extensions (if any)
                extsplit = name.partition('.')
                name = ''.join(extsplit[0] + '_' + archivelabel + extsplit[1] + extsplit[2])
        return name

    def file_exists(self, destination=None, name=None):
        """Check if a file exists."""
        filepath = f'{destination}/{name}'
        if os.path.isfile(filepath):
            self.logger.info(f'File {filepath} already exists, skipping...')
            return True
        return False

    def copy_backup(self, destination=None, name=None, source=None):
        """Copy a file."""
        self.create_destination_folder(destination_folder=destination)
        target = f'{destination}/{name}'
        copyfile(source, target)
        self.logger.info(f'Created copy of `{source}` to `{target}`')

    #
    # Create backup
    #
    def create_backup(self, backup_rename=default_backup_rename, archive_rename=default_archive_rename):
        """Do the actual backup."""

        # Update the current timestamp
        self.now = datetime.now()

        # Log
        timestamp = self.now.strftime('%Y-%m-%d %H:%M:%S')
        self.logger.info(f'Backup started at: {timestamp}')

        # Archive old backup files
        latest_file = self.get_latest_file(destination=f'{self.destination_folder}', regexp=archive_rename[0])
        if latest_file:
            self.archive(backup_file=latest_file, archive_rename=archive_rename)
            os.remove(latest_file)

        # Start the new backup
        self.logger.info(subprocess.run(self.command, stdout=subprocess.PIPE).stdout.decode('utf-8'))

        # See if we need to rename the latest file in the destination folder.
        if backup_rename:
            (re_pattern, re_replacement) = backup_rename
            latest_file = self.get_latest_file(
                destination=f'{self.destination_folder}',
                regexp=re_pattern
            )
            # It's possible that the re_pattern filter decides it
            # doesn't need renaming.
            if latest_file:
                new_name = re.sub(re_pattern, re_replacement, os.path.basename(latest_file))
                move(f'{latest_file}', f'{self.destination_folder}/{new_name}')

        # Check if we now have a file that qualifies for archiving.

        latest_file = self.get_latest_file(destination=f'{self.destination_folder}', regexp=archive_rename[0])
        if not latest_file:
            self.logger.info('No backup file that qualifies for archiving.')

        # Finish backup
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.logger.info(f'Backup finished at: {timestamp}')

    #
    # Main Rotating logic
    #
    def archive(self, backup_file=None, archive_rename=default_archive_rename):
        """
        Archive the files with respect to retention settings.

        The archive_rename tuple of regexp search and replace patterns
        is used to rename the backup file to an archive file name with
        appropriate time indication label.
        """
        schema = {
            'hourly': {
                'archivelabel': self.now.strftime('%Y-%m-%d_%H'),
                'destination': f'{self.destination_folder}/{self.hourly_folder}',
                'retention': self.hours_to_keep
            },
            'daily': {
                'archivelabel': self.now.strftime('%Y-%m-%d'),
                'destination': f'{self.destination_folder}/{self.daily_folder}',
                'retention': self.days_to_keep
            },
            'weekly': {
                'archivelabel': self.now.strftime('%Y-%V'),
                'destination': f'{self.destination_folder}/{self.weekly_folder}',
                'retention': self.weeks_to_keep
            },
            'monthly': {
                'archivelabel': self.now.strftime('%Y-%b'),
                'destination': f'{self.destination_folder}/{self.monthly_folder}',
                'retention': self.months_to_keep
            }
        }

        for key, value in schema.items():
            self.logger.info(f'Running rotation scheme `{key}` for `{self.name}`')
            archive_name = self.archive_name(
                backup_file=backup_file,
                archive_rename=archive_rename,
                archivelabel=value['archivelabel']
            )
            if not self.file_exists(destination=value['destination'], name=archive_name):
                self.copy_backup(destination=value['destination'], name=archive_name, source=backup_file)
                self.delete_old_files(destination=value['destination'], number_to_keep=value['retention'])


backup = Backup()


def run_backup(
    name=None,
    command=None,
    backup_rename=Backup.default_backup_rename,
    archive_rename=Backup.default_archive_rename,
):
    """
    Run backup and archiving process.

    See documentation of Backup.run().
    """
    backup.run(name=name, command=command, backup_rename=backup_rename, archive_rename=archive_rename)
