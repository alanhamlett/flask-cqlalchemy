# -*- coding: utf-8 -*-
"""
flask_cqlalchemy

:copyright: (c) 2015-2016 by George Thomas
:license: BSD, see LICENSE for more details

"""
from cassandra.cqlengine import connection
from cassandra.cqlengine import columns
from cassandra.cqlengine import models
from cassandra.cqlengine import usertype
from cassandra.cqlengine.connection import cluster, session
from cassandra.cqlengine.management import (
    sync_table, create_keyspace_simple, sync_type
)


class CQLAlchemy(object):
    """The CQLAlchemy class. All CQLEngine methods are available as methods of
    Model or columns attribute in this class.
    No teardown method is available as connections are costly and once made are
    ideally not disconnected.
    """

    def __init__(self, app=None):
        """Constructor for the class"""
        self.columns = columns
        self.Model = models.Model
        self.UserType = usertype.UserType
        self.app = app
        self.sync_table = sync_table
        self.sync_type = sync_type
        self.create_keyspace_simple = create_keyspace_simple
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        """Bind the CQLAlchemy object to the app.

        This method set all the config options for the connection to
        the Cassandra cluster and creates a connection at startup.
        """
        self._hosts_ = app.config['CASSANDRA_HOSTS']
        self._keyspace_ = app.config['CASSANDRA_KEYSPACE']
        self._consistency = app.config.get('CASSANDRA_CONSISTENCY', 1)
        self._lazy_connect = app.config.get('CASSANDRA_LAZY_CONNECT', False)
        self._retry_connect = app.config.get('CASSANDRA_RETRY_CONNECT', False)
        self._setup_kwargs = app.config.get('CASSANDRA_SETUP_KWARGS', {})

        if not self._hosts_ and self._keyspace_:
            raise NoConfig("""No Configuration options defined.
            At least CASSANDRA_HOSTS and CASSANDRA_CONSISTENCY
            must be supplied""")

        try:
            from uwsgidecorators import postfork
        except ImportError:  # uWSGI isn't installed
            pass
        else:
            @postfork
            def cassandra_init_uwsgi(*args, **kwargs):
                self.setup_connection()

        try:
            from celery.signals import (
                worker_process_init, beat_init, worker_shutting_down
            )
        except ImportError:  # Celery is not installed
            pass
        else:
            def cassandra_init_celery(*args, **kwargs):
                self.setup_connection()

            def cassandra_shutdown_celery(*args, **kwargs):
                self.shutdown_connection()

            worker_process_init.connect(cassandra_init_celery)
            worker_shutting_down.connect(cassandra_shutdown_celery)
            beat_init.connect(cassandra_init_celery)

        # We might be running as a script
        self.setup_connection()

    def shutdown_connection(self):
        if cluster is not None:
            cluster.shutdown()
        if session is not None:
            session.shutdown()

    def setup_connection(self):
        self.shutdown_connection()
        connection.setup(self._hosts_,
                         self._keyspace_,
                         consistency=self._consistency,
                         lazy_connect=self._lazy_connect,
                         retry_connect=self._retry_connect,
                         **self._setup_kwargs)

    def sync_db(self):
        """Sync all defined tables. All defined models must be imported before
        this method is called
        """
        models = get_subclasses(self.Model)
        for model in models:
            sync_table(model)

    def set_keyspace(self, keyspace_name=None):
        """ Changes keyspace for the current session if keyspace_name is
        supplied. Ideally sessions exist for the entire duration of the
        application. So if the change in keyspace is meant to be temporary,
        this method must be called again without any arguments
        """
        if not keyspace_name:
            keyspace_name = self.app.config['CASSANDRA_KEYSPACE']
        models.DEFAULT_KEYSPACE = keyspace_name
        self._keyspace_ = keyspace_name


class NoConfig(Exception):
    """ Raised when CASSANDRA_HOSTS or CASSANDRA_KEYSPACE is not defined"""
    pass


# some helper functions for mashing the class list
def flatten(lists):
    """flatten a list of lists into a single list"""
    return [item for sublist in lists for item in sublist]


def get_subclasses(cls):
    """get all the non abstract subclasses of cls"""
    if cls.__abstract__:
        return flatten([get_subclasses(scls) for scls in cls.__subclasses__()])
    else:
        return [cls]
