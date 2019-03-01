#!/usr/bin/env python3
"""
Docker Entrypoint

This script is called when the container is started. It uses a ClusterController class to perform actions when the
state of the cluster changes.

Depening on command line arguments actions can be performed. In each action processes can be started.
"""
import argparse
import json
import multiprocessing
import os
from time import sleep, time

import sys

from clustercontroller.clustercontroller import ClusterController, start_process, run_system_process, \
    start_cluster_controller, monitor_processes, render_config, create_logger

# Define command line arguments
parser = argparse.ArgumentParser(description='Docker Entrypoint')
parser.add_argument('-s', '--start', help="Start Cluster", action='store_true', default=False)
parser.add_argument('--standalone', help="Start Stand-Alone", action='store_true', default=False)
parser.add_argument('--makedocs', help="Make Documentation", action='store_true', default=False)
parser.add_argument('--makecheck', help="Run code checks", action='store_true', default=False)
parser.add_argument('--makecheckdocs', help="Run documentation checks", action='store_true', default=False)
parser.add_argument('--makeciunittests', help="Run documentation checks", action='store_true', default=False)
parser.add_argument('--debug', help="Run documentation checks", action='store_true', default=False)
args = parser.parse_args()


class MyAppController(ClusterController):
    """This controller manages a MyApp Cluster."""

    def start(self):
        """Called when the controller is started."""
        self.logger.info('MyAppController Started')
        # Schedule time based jobs
        self.schedule.every(1).hour.do(self.run_every_hour)
        variables = dict(os.environ)
        try:
            render_config(template_file='myapp.conf.j2', config_file='/etc/myapp/myapp.conf', variables=variables)
            render_config(template_file='aaa_init.xml', config_file='/var/opt/myapp/aaa_init.xml',
                          variables=variables)
        except Exception as error:
            logger.warning(f'Error during render_config: {error}')

    def started_as_master(self):
        """Called when the instance is started as master."""
        self.logger.info('MyAppController Started as master')

    def started_as_slave(self):
        """Called when the instance is started as slave."""
        self.logger.info('MyAppController Started as slave')

    def transition_master_to_slave(self):
        """Called when the instance is demoted from master to slave."""
        self.logger.info('MyAppController transitioned from master to slave')

    def transition_slave_to_master(self):
        """Called when the instance is promoted from slave to master."""
        self.logger.info('MyAppController transitioned from slave to master')

    def cluster_members_added(self, added_members):
        """Called when new members are added to the cluster."""
        self.logger.info(f'MyAppController found new members: {added_members}')

    def cluster_members_removed(self, removed_members):
        """Called when members where removed from the cluster."""
        self.logger.info(f'MyAppController removed members: {removed_members}')

    def terminate_controller(self, exitcode=0):
        """Called when the instance is being terminated."""
        self.logger.info('MyAppController was terminated')
        super().terminate_controller()

    def run_every_5_minutes(self):
        """Run every 5 minutes."""
        self.logger.info('MyAppController every 5 minute job started')

    def run_every_hour(self):
        """Run every hour."""
        self.logger.info('MyAppController hourly job started')
        start_process(command=['/opt/myapp/current/bin/myapp-backup', '--non-interactive'], name='backup_myapp')


if __name__ == '__main__':

    logger = create_logger(name='docker_entrypoint')
    logger.info('Docker Entrypoint started.')
    if args.debug:
        logger.info(f'Environment Variables: \n{json.dumps(dict(os.environ), indent=2)}')

    command = ['/opt/myapp/current/bin/myapp', '--foreground', '--cd', '/var/opt/myapp', '--heart',
               '-c', '/etc/myapp/myapp.conf', '--with-package-reload']

    command = ['tail', '-f', '/var/log/system.log', '>2']


    # Initialise the global processes list used to monitor active processes.
    processes = []
    # Define the multiprocessing terminate event. When this event is set all processes will start to terminate.
    cluster_controller_started_event = multiprocessing.Event()
    terminate_event = multiprocessing.Event()

    if args.makedocs:
        logger.info('Running make docs.')
        command = ['make', 'docs']
        run_system_process(command=command, name='Make Docs')

    elif args.makecheck:
        logger.info('Running make check.')
        command = ['make', 'check']
        run_system_process(command=command, name='Make Check')

    elif args.makecheckdocs:
        logger.info('Running make checkdocs.')
        command = ['make', 'checkdocs']
        run_system_process(command=command, name='Make Checkdocs')

    elif args.makeciunittests:
        logger.info('Running make ci_unit_tests.')
        command = ['make', 'ci_unit_tests']
        run_system_process(command=command, name='Make CI Unit Tests')

    elif args.standalone:
        logger.info('Starting in standalone mode.')
        # Start the process without a cluster controller
        process = start_process(command, terminate_event=terminate_event)
        processes.append((process, process.name))

    elif args.start:
        logger.info('Starting in cluster mode.')
        # Start the process with a cluster controller
        process = start_cluster_controller(name='myapp_controller',
                                           controller=MyAppController,
                                           cluster_controller_started_event=cluster_controller_started_event,
                                           terminate_event=terminate_event)
        processes.append((process, process.name))

        timeout = time() + 30
        timeout_reached = False
        while not cluster_controller_started_event.is_set():
            logger.info('Cluster Controller init not yet finished, waiting to start MyApp.')
            sleep(1)
            if time() > timeout:
                logger.warning('Timeout reached while waiting for Cluster Controller to be started.')
                terminate_event.set()
                timeout_reached = True
                sys.exit(1)

        if not timeout_reached:
            # Start the NCS process
            process = start_process(command=command, name='myapp', terminate_event=terminate_event,
                                    suppress_log_regexp=str(os.environ.get('SUPPRESS_LOG_REGEXP')).encode('utf-8'))
            processes.append((process, process.name))

    # Monitor processes, this will cause the container to stay active until one of the processes stops.
    monitor_processes(processes=processes, terminate_event=terminate_event)
    logger.info('Docker Entrypoint exited.')
