# Changelog

## 0.1.13 - 2019-06-27

* Bugfix

## 0.1.12 - 2019-06-26

* Bugfix

## 0.1.11 - 2019-06-26

* Feature: Changed ETCD_HOST to ETCD_HOSTS which now allows for a list of ETCD servers to be specified (comma seperated)

## 0.1.10 - 2019-04-3

* Feature: Remove lockfile when cluster controller exits

## 0.1.9 - 2019-04-3

* Bug: get_filesystem_lock didn't return True when no lock file existed 

## 0.1.8 - 2019-03-25

* Feature: Simple file system locking

## 0.1.7 - 2019-03-12

* Bug: Run check_active from main loop

## 0.1.6 - 2019-03-12

* Bug: Keep main process alive while terminate event is not set.

## 0.1.5 - 2019-03-12

* Feature: Run loop as thread so blocking actions in the controller do not influence refreshing of ETCD keys.

## 0.1.4 - 2019-03-7

* Bug: Removed debug logging

## 0.1.3 - 2019-03-7

* Feature: Run scheduled jobs in a separate thread
* Feature: Rotating backup functionality

## 0.1.2 - 2019-03-1

* Bug: Fix bug when ETCD can not be reached
* Feature: Retry connection to ETCD until timeout
* Feature: Added an parameter 'suppress_log_regexp' to start_process to allow for logging messages to be filtered

## 0.1.1 - 2019-02-8

* Bug: Fixed crash if no variables where defined in template ([Maikel Vallinga])
* Feature: Added possibility to provide custom template location ([Maikel Vallinga])

## 0.1.0 - 2019-02-2

* Initial release



[Maikel Vallinga]: https://github.com/maikelvallinga
