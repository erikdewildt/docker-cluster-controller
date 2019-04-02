# coding=utf-8
"""This module contains the ClusterController base class and some helper methods."""
import logging
import multiprocessing
import os
import re
import socket
import subprocess
import sys
import threading
import uuid
from pathlib import Path
from time import sleep, time

from raven import Client
from raven.handlers.logging import SentryHandler

try:
    import etcd
except ValueError as error:
    print(f'Error importing ETCD: {error}')

import schedule
from jinja2 import Environment, FileSystemLoader


def create_logger(name=None, logger=None):
    """
    Create logger instance and/or setup formatting.

    This method can be used to create a new logger with some formatting. When a logger instance is provided this logger
    will be properly setup to conform to the defined logging formatting.

    :param name: The name of the logger to be created (ignored when a logger instance is provided).
    :param logger:  An instance of a logger to be correctly setup.
    :return: A logger instance.
    """
    if not logger:
        logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    log_console = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)-30s - %(levelname)-8s - %(message)s')
    log_console.setFormatter(formatter)
    logger.addHandler(log_console)

    # Integrate Sentry logging
    if os.environ.get('SENTRY_DSN'):
        client = Client(os.environ.get('SENTRY_DSN'))
        sentry_handler = SentryHandler(client)
        sentry_handler.setLevel(logging.WARNING)
        logger.addHandler(sentry_handler)

    return logger


def render_config(template_file=None, config_file=None, variables={}, template_location='/tmp'):
    """
    Render a configuration file from a template using variables.

    :param template_location: The location to find the template
    :param template_file: The template file to be used.
    :param config_file: The config file used as output.
    :param variables: A dictionary of variables to use in the template.
    :return: None
    """

    if type(variables) is not dict:
        raise Exception("Attribute 'variables' should be a dictionary.")

    # Get variables, cast 'list items' to a list.
    for key, value in variables.items():
        if ',' in value:
            variables[key] = value.split(',')

    template = Environment(loader=FileSystemLoader(template_location)).get_template(template_file)
    with open(config_file, 'w') as output_file:
        output_file.write(template.render(**variables))
        output_file.close()


def run_system_process(command=None, terminate_event=None, name=multiprocessing.current_process().name,
                       suppress_log_regexp=None):
    """
    Start a OS process.

    :param command: Command array.
    :param terminate_event: The terminate event to subscribe.
    :param name: The name of the process.
    :param suppress_log_regexp: A regular expression to exclude log messages from being logged.
    :return: None
    """
    process = None
    logger = create_logger(name)
    logger.info(f'Started {name}', extra={'stack': True, })

    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except FileNotFoundError as error:
        logger.warning(f'Error during startup of {name}: {error}', extra={'stack': True, })

    if process:
        # While process is active
        while process.poll() is None:
            sleep(1)

            # Logging
            for line in process.stdout:
                if suppress_log_regexp and not re.search(suppress_log_regexp, line) or not suppress_log_regexp:
                    logger.info(line.rstrip().decode('utf-8'))

            for line in process.stderr:
                if suppress_log_regexp and not re.search(suppress_log_regexp, line) or not suppress_log_regexp:
                    logger.error(line.rstrip().decode('utf-8'))

            if terminate_event and terminate_event.is_set():
                process.terminate()

        if process.returncode != 0:
            logger.warning(f'Process {name} (command: {command}) stopped with returncode: {process.returncode}',
                           extra={'stack': True, })
        else:
            logger.info(f'Process {name} (command: {command}) stopped with returncode: {process.returncode}',
                        extra={'stack': True, })

        sys.exit(process.returncode)


def terminate_all_processes(processes=None, terminate_event=None, logger=None):
    """
    Terminate all running processes.

    :param processes: The list of processes to be terminated.
    :param terminate_event: The terminate event to set for terminating all processes.
    :param logger: The logger to be used.
    :return: True when succeeded.
    """
    # Set the terminate event to end the processes gracefully
    terminate_event.set()
    logging.info('Terminate signal send, waiting for processes to clean-up', extra={'stack': True, })

    # Give process the time to terminate gracefully before being terminated forcefully
    sleep(10)
    for item in processes:
        logger.info('Terminating all processes forcefully.', extra={'stack': True, })
        (process, _) = item
        process.terminate()
        process.join()  # Wait for the process to finish

    return True


def start_process(command=None, name=None, terminate_event=None, suppress_log_regexp=None):
    """
    Start a system process in multiprocessing mode.

    :param command: The command array to be executed.
    :param name: The name of the process.
    :param terminate_event: The terminate event which this process should act upon.
    :return: The process which was started
    """
    process = multiprocessing.Process(name=name, target=run_system_process,
                                      args=(command, terminate_event, name, suppress_log_regexp))
    process.start()
    return process


def start_cluster_controller(name='cluster_controller', controller=None, cluster_controller_started_event=None,
                             terminate_event=None):
    """
    Start a cluster controller instance.

    :param name: The name of the cluster controller.
    :param controller: Class name of the ClusterController to be started.
    :param cluster_controller_started_event: The event to be raised when the cc is successfully started.
    :param terminate_event: The terminate even which the cc should act upon.
    :return: The process whicch was started.
    """
    process = multiprocessing.Process(name=name, target=controller,
                                      args=(cluster_controller_started_event, terminate_event, ))
    process.start()
    return process


def monitor_processes(processes=None, terminate_event=None):
    """
    Monitor the list of processes.

    When a process is not alive anymore call the terminate_all_proccesses method to stop all processes.

    :param processes: The list tof processes to be monitored.
    :param terminate_event: The terminate event signal to be raised when a process is stopped.
    :return: None.
    """
    # Create the logger instance for multiprocessing.
    logger = create_logger(name='multiprocessing', logger=multiprocessing.get_logger())

    # Monitor processes
    while len(processes):
        sleep(1)
        for item in processes:
            # For each process check if the process is still active.
            (process, name) = item
            if not process.is_alive():
                if process.exitcode is None:
                    logger.warning(f'Process {name} not alive, unknown exitcode', extra={'stack': True, })
                else:
                    logger.warning(f'Process {name} not alive, exitcode: {process.exitcode}', extra={'stack': True, })

                # If the process is not active, wait for the process to finish and remove the process from the list.
                process.join()
                processes.remove(item)

                # When a single process is terminated then terminate all other processes as well.
                terminate_all_processes(processes=processes, terminate_event=terminate_event, logger=logger)




class ClusterController:
    """
    Base class for a cluster controller.

    This class handles the master/slave election, monitoring and failover.

    On set events methods are called to handle the state change.

    States:
        - started    : Cluster Controller is started, service is not yet active
        - running    : Cluster Controller is running, registration in ETCD has taken place, service is not yet started
        - active     : Service is active
        - stopping   : Cluster Controller is stopping
        - terminated : Cluster Controller is terminated

    """

    debug = False

    # Settings
    terminate_when_no_longer_active = os.environ.get('TERMINATE_WHEN_NO_LONGER_ACTIVE', True)

    # Environment settings
    environment = os.environ.get('ENVIRONMENT')
    service = os.environ.get('SERVICE')
    etcd_host = os.environ.get('ETCD_HOST')
    etcd_port = os.environ.get('ETCD_PORT')

    try:
        ports = os.environ.get('PORTS_WHEN_ACTIVE').split(',')
    except AttributeError:
        ports = None

    # Base variables
    logger = None
    schedule = schedule
    etcd_client = None
    etcd_error_timestamp = None
    terminate_event = None
    cluster_controller_started_event = None
    terminate_schedule_event = None
    terminate_run_event = None
    filesystem_locks = None

    # State / ID variables
    container = None
    instance_id = None
    role = None
    state = None

    # ETC key's and dir's
    master_lock = None
    lock_name = None
    members_dir = None
    master_key = None
    member_dir = None
    member_state_key = None
    member_container_key = None
    member_role_key = None
    cluster_members = []

    def __init__(self, cluster_controller_started_event=None, terminate_event=None):
        """
        Initialise the ClusterController.

        This sets some variables, registers as a member with ETC and start's the run loop
        :param terminate_event:
        """
        self.logger = create_logger(name=multiprocessing.current_process().name)
        self.logger.info("Starting Cluster Controller")
        self.state = 'started'
        self.container = os.uname()[1]
        self.instance_id = str(uuid.uuid4())
        self.terminate_event = terminate_event
        self.cluster_controller_started_event = cluster_controller_started_event

        # Check required variables
        if self.etcd_port:
            try:
                self.etcd_port = int(self.etcd_port)
            except ValueError:
                self.logger.error(f'ETCD Port should be a valid integer value.', extra={'stack': True, })
                self.state = 'stopping'

        if not isinstance(self.etcd_host, str) or not isinstance(self.etcd_port, int):
            self.logger.error(f'No valid ETCD host and/or port specified: {self.etcd_host}:{self.etcd_port}',
                              extra={'stack': True, })
            self.state = 'stopping'

        if not self.environment or not self.service:
            self.logger.error('Environment and/or service is not set.', extra={'stack': True, })
            self.state = 'stopping'

        if self.state == 'stopping':
            self.terminate_controller(exitcode=0)

        # Connect to ETCD
        connected = False

        timeout = time() + 30
        attempt = 0
        while not connected and time() < timeout:
            attempt += 1
            self.logger.info(f'Trying to connect to ETCD, attempt: {attempt}', extra={'stack': True, })
            try:
                self.etcd_client = etcd.Client(host=self.etcd_host, port=int(self.etcd_port), allow_reconnect=True)
                machines = self.etcd_client.machines
                if len(machines) >= 1:
                    connected = True
                    self.logger.info(f'Connected to ETCD machines: {machines}', extra={'stack': True, })
            except etcd.EtcdException as error:
                self.logger.info(f'Unable to connect to ETCD: {error}', extra={'stack': True, })
            sleep(1)

        if not connected:
            self.logger.warning(f'Unable to connect to ETCD, giving up...', extra={'stack': True, })
            self.state = 'stopping'
            self.terminate_controller(exitcode=1)
        else:
            # Set ETC lock name, members dir and master key location
            self.lock_name = self.environment + '_' + self.service

            self.members_dir = f"/{self.environment}/{self.service}/members"
            self.master_key = f"/{self.environment}/{self.service}/master"

            self.member_dir = f"{self.members_dir}/{self.instance_id}"
            self.member_state_key = f"{self.member_dir}/state"
            self.member_container_key = f"{self.member_dir}/container"
            self.member_role_key = f"{self.member_dir}/role"

            self.master_lock = etcd.Lock(self.etcd_client, self.lock_name)

            # Start the schedule thread
            self.terminate_schedule_event = self.run_schedule_continously(schedule=schedule, interval=1)

            # Try to acquire the mater lock.
            master = self.acquire_master_lock()

            # Start the run loop
            self.terminate_run_event = self.run()

            # Run start to include a child class startup logic and raise the init event when finished.
            self.start()
            self.cluster_controller_started_event.set()

            if master:
                self.started_as_master()
            else:
                self.started_as_slave()

            # Register in ETCD
            self.etcd_client.write(self.member_state_key, self.state, ttl=60)
            self.etcd_client.write(self.member_role_key, self.role, ttl=60)
            self.etcd_client.write(self.member_container_key, self.container, ttl=60)

            # Keep the main process alive while the terminate event is not set.
            while not self.terminate_event.is_set():
                self.check_active(ports=self.ports)
                sleep(1)

    def run_schedule_continously(self, schedule=None, interval=1):

        terminate_schedule_event = threading.Event()

        class ScheduleThread(threading.Thread):
            @classmethod
            def run(cls):
                while not terminate_schedule_event.is_set():
                    schedule.run_pending()
                    sleep(interval)

        continuous_thread = ScheduleThread()
        continuous_thread.start()
        return terminate_schedule_event

    def run(self):
        """
        Run loop for the controller.

        This loop handles all state transitions and will stop when the terminate event is set.

        :return: None
        """
        self.logger.info("Run Loop Started.")
        self.state = 'running'

        terminate_run_event = threading.Event()

        class RunThread(threading.Thread):
            @classmethod
            def run(cls):
                while not terminate_run_event.is_set():

                    if self.state in ('running', 'active'):

                        refreshed = False
                        timeout = time() + 30

                        while not refreshed and time() < timeout:
                            refreshed = self.refresh_role()
                            sleep(1)

                        if not refreshed:
                            self.state = 'stopping'
                            self.terminate_controller(exitcode=1)

                        # Check for added members.
                        added_members = set(self.get_members(state='active')) - set(self.cluster_members)
                        if added_members:
                            self.logger.info(f'Found new members: {added_members}', extra={'stack': True, })
                            self.cluster_members_added(added_members=list(added_members))

                        # Check for removed members.
                        removed_members = set(self.cluster_members) - set(self.get_members(state='active'))
                        if removed_members:
                            self.logger.info(f'Removed members: {removed_members}', extra={'stack': True, })
                            self.cluster_members_removed(removed_members=list(removed_members))

                        # Display list of members when there was a change.
                        if added_members or removed_members:
                            self.cluster_members = self.get_members(state='active')
                            self.logger.info(f'Members: {self.cluster_members}', extra={'stack': True, })

                        # Handle filesystem locks
                        if self.filesystem_locks:
                            for folder in self.filesystem_locks:
                                self.get_filesystem_lock(folder)

                    # When the terminate event is set, terminate the controller.
                    if self.terminate_event.is_set():
                        self.logger.info('Stopping Cluster Controller', extra={'stack': True, })
                        self.state = 'stopping'
                        self.terminate_controller(exitcode=0)
                        sys.exit(0)

                    sleep(1)

        continuous_thread = RunThread()
        continuous_thread.start()
        return terminate_run_event

    def terminate_controller(self, exitcode=0):
        """
        Terminate the controller.


        :return:
        """
        self.logger.info('Terminating Cluster Controller', extra={'stack': True, })

        if self.state == 'stopping':

            # Clean up stuff before exiting...
            try:
                if self.release_master_lock():
                    self.logger.info('Master Lock released', extra={'stack': True, })

                if self.etcd_client and self.etcd_client.delete(self.member_dir, recursive=True):
                    self.logger.info('Member removed from ETCD.', extra={'stack': True, })
            except etcd.EtcdException:
                pass

            self.terminate_schedule_event.set()
            self.terminate_run_event.set()
            self.terminate_event.set()

            self.state = 'terminated'
            self.logger.info('Cluster Controller Terminated.', extra={'stack': True, })
            sys.exit(exitcode)
        else:
            self.logger.info('Terminate Controller called while state not in stopping state.', extra={'stack': True, })

    def acquire_master_lock(self):
        """
        Try to acquire the master lock.

        :return: True when successful, false when not.
        """
        old_role = self.role

        try:
            if self.master_lock.acquire(blocking=False, lock_ttl=30):
                self.role = 'master'
                self.etcd_client.write(self.master_key, self.instance_id, ttl=30)

                if old_role == 'slave':
                    self.transition_slave_to_master()

                if old_role != 'master':
                    self.etcd_client.write(self.member_role_key, self.role, ttl=30)
                    self.logger.info(f'Instance {self.instance_id} on Container {self.container} became {self.role}',
                                     extra={'stack': True, })

                return True
        except etcd.EtcdException as error:
            self.logger.warning(f'Error while trying to require master lock: {error}',
                                extra={'stack': True, })

        self.role = 'slave'

        if old_role == 'master':
            self.transition_master_to_slave()

        if old_role != 'slave':
            self.etcd_client.write(self.member_role_key, self.role, ttl=30)
            self.logger.info(f'Instance {self.instance_id} on Container {self.container} became {self.role}',
                             extra={'stack': True, })

        return False

    def release_master_lock(self):
        """
        Release the master lock.

        :return: True when successful, false when not.
        """
        if self.role == 'master':
            if self.master_lock.release():
                self.etcd_client.delete(self.master_key)
                self.role = 'slave'
                self.logger.info(f'Instance {self.instance_id} on Container {self.container} released master lock',
                                 extra={'stack': True, })
                self.logger.info(f'Instance {self.instance_id} on Container {self.container} became {self.role}',
                                 extra={'stack': True, })
                self.transition_master_to_slave()
                return True
        return False

    def refresh_role(self):
        """
        Refresh the current role and member registration in ETCD.

        :return: None
        """
        # Refresh ETCD registration
        etcd_connection_failed = False

        try:
            self.etcd_client.refresh(self.member_state_key, ttl=10)
        except etcd.EtcdKeyNotFound:
            self.etcd_client.write(self.member_state_key, self.state, ttl=10)
        except etcd.EtcdConnectionFailed:
            etcd_connection_failed = True
            self.logger.error('Connection to ETCD failed.', extra={'stack': True, })

        try:
            self.etcd_client.refresh(self.member_role_key, ttl=10)
        except etcd.EtcdKeyNotFound:
            self.etcd_client.write(self.member_role_key, self.role, ttl=10)
        except etcd.EtcdConnectionFailed:
            etcd_connection_failed = True
            self.logger.error('Connection to ETCD failed.', extra={'stack': True, })

        try:
            self.etcd_client.refresh(self.member_container_key, ttl=10)
        except etcd.EtcdKeyNotFound:
            self.etcd_client.write(self.member_container_key, self.container, ttl=10)
        except etcd.EtcdConnectionFailed:
            etcd_connection_failed = True
            self.logger.error('Connection to ETCD failed.', extra={'stack': True, })

        # Refresh master lock
        if self.role == 'master':
            # If we are master, just refresh the master lock and key
            try:
                self.master_lock.acquire(blocking=False, lock_ttl=10)
            except etcd.EtcdConnectionFailed:
                etcd_connection_failed = True
                self.logger.error('Connection to ETCD failed.', extra={'stack': True, })

            try:
                self.etcd_client.refresh(self.master_key, ttl=10)
            except etcd.EtcdKeyNotFound:
                self.etcd_client.write(self.master_key, self.container, ttl=10)
            except etcd.EtcdConnectionFailed:
                etcd_connection_failed = True
                self.logger.error('Connection to ETCD failed.', extra={'stack': True, })

        elif self.role == 'slave':
            # If we are slave, try to promote to master (in case master has gone away)
            self.acquire_master_lock()

        if etcd_connection_failed:
            return False

        return True

    def get_members(self, environment=None, service=None, state=None, role=None):
        """
        Get the current list of cluster members.

        When no environment and/or service is specified the instance's own environment and/or service is used.

        When no state is specified all members are returned.

        :param environment: The environment for which members should be returned.
        :param service: The service for which members should be returned.
        :param state: A state which is used as a filter for members.
        :param role: The role members should have
        :return: A list of member instance id's
        """
        if environment is None:
            environment = self.environment
        if service is None:
            service = self.service

        members_dir = f"/{environment}/{service}/members/"

        members = []
        directory = None

        try:
            directory = self.etcd_client.get(members_dir)
        except etcd.EtcdKeyNotFound as error:
            self.logger.debug(f'Member dir not found: {error}', extra={'stack': True, })
        except etcd.EtcdException:
            self.logger.error('Connection to ETCD failed.', extra={'stack': True, })

        if directory:
            for result in directory.children:
                instance = str(result.key).split('/')[-1]
                if instance != self.instance_id:
                    if state is not None:
                        try:

                            if state and not role:
                                # When filtered only on state
                                if self.etcd_client.read(members_dir + instance + '/state').value == state:
                                    members.append(instance)
                            elif role and not state:
                                # When filtered only on role
                                if self.etcd_client.read(members_dir + instance + '/role').value == role:
                                    members.append(instance)
                            elif state and role:
                                # When filtered on both state and role
                                if self.etcd_client.read(members_dir + instance + '/state').value == state and \
                                        self.etcd_client.read(members_dir + instance + '/role').value == role:
                                    members.append(instance)

                        except etcd.EtcdKeyNotFound as error:
                            self.logger.debug(f'Member dir found with no state key: {error}',
                                              extra={'stack': True, })
                        except etcd.EtcdException:
                            self.logger.error('Connection to ETCD failed.', extra={'stack': True, })
                    else:
                        members.append(instance)

        return members

    def get_container_id(self, environment=None, service=None, instance_id=None):
        """
        Get the container id.

        :param environment: The environment for which members should be returned.
        :param service: The service for which members should be returned.
        :param instance_id: The id of a member.
        :return: container id
        """
        container = None
        try:
            member_key = f"/{environment}/{service}/members/{instance_id}/container/"
            container = self.etcd_client.get(member_key).value

        except etcd.EtcdKeyNotFound as error:
            self.logger.info(f"Key can't be found {error}", extra={'stack': True, })

        return container

    def check_active(self, ports=None):
        """
        Check if service is active by trying if ports are opened.

        :param ports:
        :return:
        """
        active = True
        oldstate = self.state

        if ports:
            for port in ports:
                try:
                    socket.create_connection(address=('127.0.0.1', int(port)), timeout=5)
                except socket.error as error:
                    self.logger.info(f'Connection to port {port} failed: {error}',
                                     extra={'stack': True, })
                    active = False
                    break

        if active:
            if oldstate == 'running':
                self.logger.info(f'Successfully connected to ports: {ports}', extra={'stack': True, })
                self.became_active()
            self.state = 'active'
        else:
            self.state = 'running'

        if oldstate == 'active' and self.state == 'running' and self.terminate_when_no_longer_active:
            # When ports are no longer active terminate controller.
            self.logger.info('Port(s) are no longer active, terminating controller.',
                             extra={'stack': True, })
            self.state = 'stopping'
            self.terminate_controller(exitcode=1)

        try:
            self.etcd_client.write(self.member_state_key, self.state, ttl=30)
        except etcd.EtcdException:
            self.logger.error('Could not update state, connection to ETCD failed.',
                              extra={'stack': True, })

    def wait_for_service(self, service=None, timeout=60):
        """
        Wait for a service to be active.

        :param service: The service which needs to be active
        :param timeout: The timeout to limit infinite wait
        :return:
        """
        active_members = []
        timeout = time() + timeout
        self.logger.info(f'Waiting for service {service} to become active.')

        while len(active_members) == 0:
            # Get the active members
            active_members = self.get_members(environment=self.environment, service=service, state='active',
                                              role='master')

            if time() > timeout:
                self.logger.warning(f'Timeout reached while waiting for service {service} to become active.',
                                    extra={'stack': True, })
                return False

            sleep(1)

        self.logger.info(f'Service {service} became active.')
        return True

    def get_filesystem_lock(self, path):
        """
        Try to get a system lock file.

        If the lockfile is from the current container the timestamp is refreshed.
        If the lockfile is from an other container but the timestamp is to old, the lockfile is removed and a new
        lockfile for the current container is created.

        :param path: The path for which a lock is required.
        :return: True when the lock is owned by the current container, False when not.
        """
        write_new_lockfile = False
        lock_container = False

        lockfile_path = Path(str(path).rstrip('/') + '/lock')
        current_timestamp = int(round(time() * 1000))

        if lockfile_path.is_file():
            with open(lockfile_path, 'r') as lockfile:
                lock_content = lockfile.read()
                lock_container = lock_content.split(':')[0]
                lock_timestamp = int(lock_content.split(':')[1])

                if lock_container == self.container and lock_timestamp + 10000 <= current_timestamp or \
                        lock_content != self.container and lock_timestamp + 30000 < current_timestamp:
                    write_new_lockfile = True
        else:
            write_new_lockfile = True

        if write_new_lockfile:
            with open(lockfile_path, 'w') as lockfile:
                lock_content = f'{self.container}:{current_timestamp}'
                lockfile.write(lock_content)
                self.logger.debug(f'Wrote lockfile {lockfile_path}')

        if lock_container == self.container:
            return True
        else:
            return False

    def start(self):
        """
        Run when started.

        Placeholder for the start method implemented and used in a Child instance.

        :return:
        """
        pass

    def started_as_master(self):
        """
        Run when instance got started as master.

        Placeholder for the started_as_master method implemented and used in a Child instance.

        :return:
        """
        pass

    def started_as_slave(self):
        """
        Run when started as slave.

        Placeholder for the started_as_slave method implemented and used in a Child instance.

        :return:
        """
        pass

    def transition_master_to_slave(self):
        """
        Run when `Transition Master to Slave` occurs.

        Placeholder for the transition_master_to_slave method implemented and used in a Child instance.

        :return:
        """
        pass

    def transition_slave_to_master(self):
        """
        Run when `Transistion Slave to Master` occurs.

        Placeholder for the transition_slave_to_master method implemented and used in a Child instance.

        :return:
        """
        pass

    def cluster_members_added(self, added_members):
        """
        Run when cluster members got added.

        Placeholder for the cluster_members_added method implemented and used in a Child instance.

        :return:
        """
        pass

    def cluster_members_removed(self, removed_members):
        """
        Run when cluster members got removed.

        Placeholder for the cluster_members_added method implemented and used in a Child instance.

        :return:
        """
        pass

    def became_active(self):
        """
        Run when instance became active.

        Placeholder for the became_active method implemented and used in a Child instance.

        :return:
        """
        pass

    def run_every_hour(self):
        """
        Run every hour.

        Placeholder for the run_every_hour method implemented and used in a Child instance.

        :return:
        """
        pass
