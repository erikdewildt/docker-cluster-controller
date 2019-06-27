# Docker Cluster Controller

This project provides a 'clustercontroller' package which can be used to create a docker-entrypoint.

In complex docker swarm setups the order in which containers are started cannot be controlled (depends_on). When there
is a need to have different actions depening on boot order this has to be handled during initialisation of the 
container.

The clustercontroller package provides a class which can be used in a docker-entrypoint. 

In the docker-entrypoint multiprocessing is used through methods provided by the package to start two main processes:

1. ClusterController process
2. The actual service the container needs to provide

Both processes are registered and actively monitored. If one of both processes (unexpectedly) terminates the other
is gracefully terminated using terminate signals.

The ClusterController registers the instance in ETCD and tries to aquire a master role. Depending on the boot order
of containers it will either get the master role or become slave.

Depending on the role methods are executed during initialisation, during it's lifecycle any state transfer will also
call appropriate actions for handling these events.

During startup of the controller 'scheduled' jobs can be registered for example to perform hourly actions. It is
important to only use multiprocessing task using the 'start_process' method within these time based methods to 'freeze'
any other processes.



## Installation:

pip install docker-cluster-controller


## Usage:

1. Build a container with a docker-entrypoint using the clustercontroller. See the docker-entrypoint.py as and example implementation.
1. Start a ETCD Cluster, see [docker-service-discovery]
2. In the docker-compose file set environment variables so the clustercontroller knows where and how to register

|Environment Variable |Description |
|---------------------|------------|
|ETCD_HOSTS |The hostnames of the ETCD node (comma seperated) |
|ETCD_PORT |The port of the ETCD node |
|PORTS_WHEN_ACTIVE | The port(s) when de service has become active (e.g. 80,443,8443)
|ENVIRONMENT: | A single ETCD node can be used for multimple environments, therefore the environment has to be specified. E.g. development'|
|SERVICE: |The name of the service |

## Backup:

To use the rotating backup functionality some environemnt variables have to be set:

|Environment Variable |Description |
|---------------------|------------|
|BACKUP_HOURS_TO_KEEP=24 |The number of hourly backups to keep |
|BACKUP_DAYS_TO_KEEP=14 |The number of daily backups to keep |
|BACKUP_WEEKS_TO_KEEP=4 |The number of weekly backups to keep |
|BACKUP_MONTHS_TO_KEEP=3 |The number of monthly backups to keep |
|BACKUP_DESTINATION_FOLDER=backup |The backup destination folder |

Within a scheduled method the backup can be called:

```python
    run_backup(name='myapp_backup', command=['backup_command', '-x', 'some_option', '-y', 'some_other_option'])
```


## Filesystem locks

When starting the controller a tuple with some file system paths can be specified. The controller then make sures a
lockfile is created for the current container in the path(s) specified.

```python
    self.filesystem_locks= ('backup', )
```

The 'get_filesystem_lock' method will return True if the current container has a lock for the path or False if another
container has a lock in place.

```python
    self.get_filesystem_lock('backup')
```

[docker-service-discovery]: https://github.com/erikdewildt/docker-service-discovery
