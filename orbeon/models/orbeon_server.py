# -*- coding: utf-8 -*-
##############################################################################
# Author: Open2Bizz (www.open2bizz.nl)
# Employee: Dennis Ochse
# Date: 2019-05-02
#
# GNU LESSER GENERAL PUBLIC LICENSE
# Version 3, 29 June 2007
##############################################################################

import fcntl
import logging
import os
import tempfile
import threading
import urllib.request

from lxml import etree

from odoo import SUPERUSER_ID, api, fields, models
from odoo.exceptions import ValidationError
from odoo.modules.registry import Registry

from .. import services

_logger = logging.getLogger(__name__)

ORBEON_PERSISTENCE_SERVER_PREFIX = 'orbeon.persistence.server'
ORBEON_PERSISTENCE_SERVER_INTERFACE = '0.0.0.0'

PERSISTENCE_SERVER_SINGLE_THREADED = 'SINGLE_THREADED'
PERSISTENCE_SERVER_MULTI_THREADED = 'MULTI_THREADED'
PERSISTENCE_SERVER_FORKING = 'FORKING'


# Inter-process ownership of persistence-server TCP ports.
#
# With Odoo workers > 0, multiple processes can load the same registry. A
# normal Python global is therefore not enough to prevent duplicate starts.
# Linux flock() gives exactly one Odoo process ownership of a configured port.
# The kernel automatically releases the lock when that process dies, including
# during systemd stop/restart.
_PERSISTENCE_PORT_LOCKS = {}
_PERSISTENCE_LOCK_GUARD = threading.Lock()


def _persistence_lock_path(port):
    port = int(port)
    return os.path.join(
        tempfile.gettempdir(),
        'odoo-orbeon-persistence-%s.lock' % port,
    )


def _try_acquire_persistence_port_lock(port):
    port = int(port)

    with _PERSISTENCE_LOCK_GUARD:
        current = _PERSISTENCE_PORT_LOCKS.get(port)
        if current and not current.closed:
            return True

        handle = open(_persistence_lock_path(port), 'a+', encoding='ascii')

        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            handle.close()
            return False

        handle.seek(0)
        handle.truncate()
        handle.write(str(os.getpid()))
        handle.flush()

        _PERSISTENCE_PORT_LOCKS[port] = handle

        _logger.info(
            'Odoo process %s acquired Orbeon persistence port lock for %s',
            os.getpid(),
            port,
        )
        return True


def _release_persistence_port_lock(port):
    port = int(port)

    with _PERSISTENCE_LOCK_GUARD:
        handle = _PERSISTENCE_PORT_LOCKS.pop(port, None)
        if not handle:
            return False

        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()

        _logger.info(
            'Odoo process %s released Orbeon persistence port lock for %s',
            os.getpid(),
            port,
        )
        return True


def _autostart_after_registry_commit(dbname):
    """Start configured persistence servers after registry loading committed.

    Do not reuse the environment from ``_register_hook`` here. By the time
    this callback is called, that cursor has just been committed and may be
    about to be closed. Create a fresh cursor/environment instead.
    """
    try:
        registry = Registry(dbname)
        with registry.cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})
            env['orbeon.server']._autostart_persistence_servers()
            cr.commit()
    except Exception:
        _logger.exception(
            "Unable to autostart Orbeon persistence server(s) for database %s",
            dbname,
        )


class OrbeonThreadedWSGIServer(threading.Thread):

    def __init__(self, name, server, stopper):
        super().__init__(name=str(name), daemon=True)
        self.server = server
        self.stopper = stopper

    def run(self):
        try:
            self.server.serve_forever()
        except Exception:
            # Do not log a normal shutdown as an error.
            if not self.stopper.is_set():
                _logger.exception(
                    "Unexpected exception in Orbeon persistence server thread %s",
                    self.name,
                )
        finally:
            try:
                self.server.server_close()
            except Exception:
                _logger.exception(
                    "Unable to close Orbeon persistence server thread %s",
                    self.name,
                )
            finally:
                port = getattr(self, 'persistence_port', None)
                if port is not None:
                    _release_persistence_port_lock(port)


class OrbeonServer(models.Model):
    _name = 'orbeon.server'
    _inherit = ['mail.thread']
    _description = 'Orbeon Server'

    _rec_name = 'url'

    name = fields.Char(
        'Name',
        required=True,
    )

    url = fields.Char(
        'URL',
        help='URL relative to Odoo server, the Odoo server will open the URL and proxy the response',
        required=True,
    )

    description = fields.Text(
        'Description',
    )

    persistence_server_port = fields.Char(
        'Port',
        required=True,
    )

    persistence_server_processtype = fields.Selection(
        [
            (PERSISTENCE_SERVER_SINGLE_THREADED, 'Single threaded'),
            (PERSISTENCE_SERVER_MULTI_THREADED, 'Multi threaded'),
            (PERSISTENCE_SERVER_FORKING, 'Forking (process)'),
        ],
        'Process-type',
        default=PERSISTENCE_SERVER_SINGLE_THREADED,
        required=True,
    )

    persistence_server_configfile_path = fields.Char(
        'Config-file path',
        help=(
            'If specified, the Odoo connection is setup with its config, '
            'from file in given path. '
            'If blank, the Orbeon HTTP-Headers will be used.'
        ),
    )

    persistence_server_active = fields.Boolean(
        'Active',
        default=False,
        help='Provisioning the persistence-server is enabled if active is checked (True).',
    )

    persistence_server_autostart = fields.Boolean(
        'Autostart',
        default=False,
        help='Ensures the persistence-server will be started right after Odoo starts',
    )

    # Runtime state. This deliberately is NOT a computed field.
    persistence_server_uuid = fields.Char(
        'UUID (thread)',
        readonly=True,
        copy=False,
    )

    builder_template_ids = fields.One2many(
        'orbeon.builder.template',
        'server_id',
        string='Builder Form templates',
    )

    builder_templates_created = fields.Boolean(
        'Builder Form Templates Created',
        default=False,
        help=(
            'Whether Builder Form Templates had been created. '
            'Unset to delete and re-create Builder Template Forms.'
        ),
    )

    def _register_hook(self):
        """Schedule persistence-server autostart after registry loading.

        This is intentionally enabled with Odoo workers > 0. Multiple workers
        may reach this hook, but the actual start is protected by a per-port
        Linux flock, so only one process can own a persistence listener.
        """
        res = super()._register_hook()
        dbname = self.env.cr.dbname

        self.env.cr.postcommit.add(
            lambda dbname=dbname: _autostart_after_registry_commit(dbname)
        )

        return res

    @api.constrains('name')
    def constraint_unique_name(self):
        for record in self:
            duplicate = self.search_count([
                ('name', '=', record.name),
                ('id', '!=', record.id),
            ])
            if duplicate:
                raise ValidationError(
                    "Server with name '%s' already exists!" % record.name
                )

    @api.constrains('url')
    def constraint_unique_url(self):
        for record in self:
            duplicate = self.search_count([
                ('url', '=', record.url),
                ('id', '!=', record.id),
            ])
            if duplicate:
                raise ValidationError(
                    "Server with URL '%s' already exists!" % record.url
                )

    def start_persistence_server(self, context=None, *args, **kwargs):
        self.ensure_one()

        if not self.persistence_server_active:
            raise ValidationError(
                "Server with name %s can't start, because marked inactive."
                % self.name
            )

        if self._is_persistence_server_running():
            _logger.info(
                "Orbeon persistence server '%s' is already running locally "
                "on port %s (thread: %s)",
                self.name,
                self.persistence_server_port,
                self.persistence_server_uuid,
            )
            return True

        try:
            port = int(self.persistence_server_port)
        except (TypeError, ValueError) as e:
            raise ValidationError(
                "Invalid persistence-server port: %s" % self.persistence_server_port
            ) from e

        if not _try_acquire_persistence_port_lock(port):
            _logger.info(
                "Orbeon persistence server '%s' on port %s is already owned "
                "by another Odoo process; not starting a duplicate.",
                self.name,
                port,
            )
            return True

        try:
            if self.persistence_server_uuid:
                self.persistence_server_uuid = False

            uuid = self._new_persistence_server_uuid()

            self._start_persistence_server(
                uuid,
                port,
                self.persistence_server_processtype,
                self.persistence_server_configfile_path or '',
            )

            self.persistence_server_uuid = uuid
            self.create_orbeon_builder_templates()
            return True

        except Exception as e:
            _release_persistence_port_lock(port)
            _logger.exception(
                "Unable to start Orbeon persistence server '%s'",
                self.name,
            )
            raise ValidationError(
                "Unable to start persistence server '%s': %s" % (self.name, e)
            ) from e

    def stop_persistence_server(self, context=None, *args, **kwargs):
        self.ensure_one()

        stopped = self._stop_persistence_server(
            self.persistence_server_uuid,
            self.persistence_server_port,
        )

        if stopped:
            self.persistence_server_uuid = False
            return True

        # In multi-worker mode the UI request can land on another worker.
        # Do not clear the UUID while another process may still own the server.
        raise ValidationError(
            "The persistence server is owned by another Odoo worker. "
            "Restart the Odoo service to stop it cleanly."
        )

    @api.model
    def _new_persistence_server_uuid(self):
        from uuid import uuid4
        return str(uuid4())

    @api.model
    def _persistence_wsgi_server(self, processtype):
        from werkzeug.serving import (
            BaseWSGIServer,
            ForkingWSGIServer,
            ThreadedWSGIServer,
        )

        if processtype == PERSISTENCE_SERVER_SINGLE_THREADED:
            return BaseWSGIServer
        if processtype == PERSISTENCE_SERVER_MULTI_THREADED:
            return ThreadedWSGIServer
        if processtype == PERSISTENCE_SERVER_FORKING:
            return ForkingWSGIServer

        raise ValidationError(
            'Unknown persistence-server process type: %s' % processtype
        )

    def _is_persistence_server_running(self):
        self.ensure_one()

        if not self.persistence_server_uuid:
            return False

        uuid = str(self.persistence_server_uuid)

        return any(
            thread.name == uuid and thread.is_alive()
            for thread in threading.enumerate()
        )

    @api.model
    def _autostart_persistence_servers(self):
        """Start active servers marked for autostart.

        Safe with multiple Odoo workers: a non-blocking Linux file lock is
        acquired per TCP port. Only the owning process starts the embedded
        Werkzeug listener.
        """
        servers = self.sudo().search([
            ('persistence_server_active', '=', True),
            ('persistence_server_autostart', '=', True),
        ])

        for server in servers:
            if server._is_persistence_server_running():
                _logger.info(
                    "Orbeon persistence server '%s' already running locally "
                    "on port %s (thread: %s); skipping autostart.",
                    server.name,
                    server.persistence_server_port,
                    server.persistence_server_uuid,
                )
                continue

            try:
                port = int(server.persistence_server_port)
            except (TypeError, ValueError):
                _logger.error(
                    "Invalid persistence-server port '%s' for '%s'",
                    server.persistence_server_port,
                    server.name,
                )
                continue

            if not _try_acquire_persistence_port_lock(port):
                _logger.info(
                    "Orbeon persistence server '%s' on port %s is already "
                    "owned by another Odoo process; skipping autostart.",
                    server.name,
                    port,
                )
                continue

            try:
                if server.persistence_server_uuid:
                    _logger.info(
                        "Replacing stale persistence server UUID %s for '%s'",
                        server.persistence_server_uuid,
                        server.name,
                    )
                    server.persistence_server_uuid = False

                uuid = server._new_persistence_server_uuid()

                server._start_persistence_server(
                    uuid,
                    port,
                    server.persistence_server_processtype,
                    server.persistence_server_configfile_path or '',
                )

                server.persistence_server_uuid = uuid

                _logger.info(
                    "Autostarted Orbeon persistence server '%s' on port %s "
                    "(thread: %s, Odoo pid: %s)",
                    server.name,
                    port,
                    uuid,
                    os.getpid(),
                )

            except Exception:
                _release_persistence_port_lock(port)
                _logger.exception(
                    "Unable to autostart Orbeon persistence server '%s' on port %s",
                    server.name,
                    port,
                )

    @api.model
    def _start_persistence_server(
        self,
        uuid,
        port,
        processtype,
        configfile_path=None,
    ):
        app = services.persistence_server.wsgi_server.create_app(
            configfile_path or ''
        )
        wsgi_server = self._persistence_wsgi_server(processtype)

        try:
            port_number = int(port)
        except (TypeError, ValueError) as e:
            raise ValidationError(
                "Invalid persistence-server port: %s" % port
            ) from e

        wsgi_app_server = wsgi_server(
            ORBEON_PERSISTENCE_SERVER_INTERFACE,
            port_number,
            app,
        )

        stopper = threading.Event()
        thread = OrbeonThreadedWSGIServer(
            name=str(uuid),
            server=wsgi_app_server,
            stopper=stopper,
        )
        thread.persistence_port = port_number

        _logger.info(
            'Starting HTTP (werkzeug) %s (thread: %s) on port %s',
            ORBEON_PERSISTENCE_SERVER_PREFIX,
            uuid,
            port_number,
        )

        thread.start()

    @api.model
    def _stop_persistence_server(self, uuid, port):
        if not uuid:
            return False

        uuid = str(uuid)

        for thread in threading.enumerate():
            if thread.name != uuid:
                continue

            _logger.info(
                'Stopping HTTP (werkzeug) %s (thread: %s) on port %s',
                ORBEON_PERSISTENCE_SERVER_PREFIX,
                uuid,
                port,
            )

            thread.stopper.set()

            # shutdown() tells serve_forever() to exit cleanly. The thread's
            # finally block closes the socket and releases the process lock.
            thread.server.shutdown()
            thread.join(timeout=5.0)

            if thread.is_alive():
                _logger.warning(
                    "Orbeon persistence server thread %s did not stop within 5 seconds",
                    uuid,
                )
                return False

            return True

        _logger.info(
            'No live Orbeon persistence server thread %s found on port %s',
            uuid,
            port,
        )
        return False

    def create_orbeon_builder_templates(self):
        self.ensure_one()

        if self.builder_templates_created:
            return

        # XXX Once the listing (HTTP) request doesn't fail (HTTP 500),
        # this can be changed to a loop through all Orbeon example forms.
        #
        # According to:
        # https://doc.orbeon.com/form-runner/api/persistence/forms-metadata.html
        # HTTP GET on: /fr/service/persistence/form
        form_names = ['contact', 'controls']

        for form_name in form_names:
            url = None
            try:
                url = (
                    'http://%s/fr/service/persistence/crud/orbeon/%s/form/form.xhtml'
                    % (self.url, form_name)
                )
                request = urllib.request.Request(url)
                result = urllib.request.urlopen(request)
                data = result.read()

                parser = etree.XMLParser(recover=True, encoding='utf-8')
                xml_root = etree.XML(data, parser)

                # TODO FIXME: multiple title nodes (by language)
                form_name = xml_root.xpath('//metadata/form-name')[0].text
                xml = etree.tostring(xml_root)

                # First delete all related builder templates
                self.builder_template_ids.filtered(
                    lambda r: r.fetched_from_orbeon and r.form_name == form_name
                ).unlink()

                self.env['orbeon.builder.template'].create({
                    'server_id': self.id,
                    'module_id': self.env['ir.model.data'].xmlid_to_res_id(
                        'base.module_orbeon'
                    ),
                    'form_name': form_name,
                    'xml': xml,
                    'fetched_from_orbeon': True,
                })

                self.builder_templates_created = True
            except Exception:
                _logger.exception(
                    'Orbeon request failed: %s',
                    url,
                )
