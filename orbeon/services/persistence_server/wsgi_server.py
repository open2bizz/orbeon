# -*- coding: utf-8 -*-
##############################################################################
# Author: Open2Bizz (www.open2bizz.nl)
# Employee: Dennis Ochse
# Date: 2019-05-02 (updated 2025-08-26)
#
# GNU LESSER GENERAL PUBLIC LICENSE v3
##############################################################################
import base64
import logging
from xml.etree import ElementTree as ET

from werkzeug.wrappers import Request, Response
from werkzeug.exceptions import MethodNotAllowed, InternalServerError

from .orbeon_handlers import BuilderHandler, RunnerHandler, OdooServiceHandler
from .. import utils
from odoo.tools import config

_logger = logging.getLogger(__name__)
_log = utils._log

BUILDER_HANDLER = 'builder_handler'
RUNNER_HANDLER = 'runner_handler'
ODOO_SERVICE_HANDLER = 'odoo_service_handler'

SEARCH_MIMETYPE = "application/xml"   # Adjust to "application/json" if your handler/search returns JSON.


class OrbeonRequestHandler(object):
    """Orbeon (HTTP) request handler"""

    def __init__(self, request, configfile_path=None, wsgi_input=None):
        # Prefer explicit path from caller; fall back to standard Odoo path
        configfile_path = configfile_path or '/etc/odoo-server.conf'
        _log("debug", "configfile_path => %s" % configfile_path)

        self.request = request
        self.path = request.path.split("/")
        self.args = request.args

        # Handle chunked encoding (Orbeon > 2016)
        if request.headers.get('Transfer-Encoding', '') == 'chunked' and request.headers.get('Content-Length', ' ') != ' ':
            body = b''
            if wsgi_input is not None:
                size_line = wsgi_input.readline()
                try:
                    size = int(size_line, 16)
                except Exception:
                    size = 0
                while size > 0:
                    body += wsgi_input.read(size + 2)[:-2]
                    try:
                        size = int(wsgi_input.readline(), 16)
                    except Exception:
                        size = 0
            self.data = body
        else:
            self.data = request.data

        # Parsed attrs from the path
        self.namespace = None
        self.app = None
        self.form = None
        self.data_type = None
        self.set_path_attrs()

        self.handler_type = None
        self.set_handler_type()

        self.handler = None
        self.set_handler()

        # Configure XML-RPC
        if configfile_path is not None:
            self.handler.set_config_by_file_path(configfile_path)

        if self.handler.config is not None and len(self.handler.config.sections()) > 0:
            self.handler.set_xmlrpc_by_config(request)
        else:
            # Build from headers (fallback)
            url = "http://%s:%s" % (
                request.headers.get("Openerp-Server"),
                request.headers.get("Openerp-Port"),
            )
            db = request.headers.get("Openerp-Database")

            # Preferred: credentials from Odoo config
            usr = str(config.get("orbeon_user"))
            passwd = str(config.get("orbeon_password"))

            # Optional: honor Basic Authorization header if present
            auth_hdr = request.headers.get("Authorization")
            if auth_hdr and auth_hdr.startswith("Basic "):
                try:
                    decoded = base64.b64decode(auth_hdr.split(" ", 1)[1]).decode("utf-8")
                    # Format is "user:pass"
                    u, p = decoded.split(":", 1)
                    usr = u or usr
                    passwd = p or passwd
                except Exception:
                    # Ignore malformed header; keep config creds
                    pass

            # NEVER log credentials
            self.handler.set_xmlrpc(db, usr, passwd, url)

    def set_path_attrs(self):
        """Set Request path-components to object attributes following:
           https://doc.orbeon.com/form-runner/api/persistence
           Expect: /{namespace}/{app}/{form}/{data_type}/...
        """
        # path[0] is '', because leading slash
        if len(self.path) > 1:
            self.namespace = self.path[1]
        if len(self.path) > 2:
            self.app = self.path[2]
        if len(self.path) > 3:
            self.form = self.path[3]
        if len(self.path) > 4:
            self.data_type = self.path[4]

    def set_handler_type(self):
        """Get Orbeon handler type (class)"""
        # /crud/orbeon/builder/...
        if self.namespace == 'crud' and self.app == 'orbeon' and self.form == 'builder':
            self.handler_type = BUILDER_HANDLER
        # /crud/{app}/runner/...
        elif self.namespace == 'crud' and self.form == 'runner':
            self.handler_type = RUNNER_HANDLER
        # /erp/...
        elif self.namespace == 'erp':
            self.handler_type = ODOO_SERVICE_HANDLER
        # /search/orbeon/builder/...
        elif self.namespace == 'search' and self.app == 'orbeon' and self.form == 'builder':
            self.handler_type = BUILDER_HANDLER
        else:
            self.handler_type = None

    def set_handler(self):
        """Instantiate the proper handler based on handler_type"""
        if self.handler_type == BUILDER_HANDLER:
            self.handler = BuilderHandler(self.app, self.form, self.data_type, self.path, self.args, self.data)
        elif self.handler_type == RUNNER_HANDLER:
            self.handler = RunnerHandler(self.app, self.form, self.data_type, self.path, self.args, self.data)
        elif self.handler_type == ODOO_SERVICE_HANDLER:
            self.handler = OdooServiceHandler(self.app, self.form, self.data_type, self.path, self.args, self.data)
        else:
            raise InternalServerError("No OrbeonResource handler for namespace=%s app=%s." % (self.namespace, self.app))

    def _wrap_response(self, payload, default_mimetype="text/plain", status=200):
        """Normalize handler outputs into a Werkzeug Response."""
        if isinstance(payload, Response):
            return payload
        if payload is None:
            payload = ""  # Avoid NoneType downstream
        return Response(payload, status=status, mimetype=default_mimetype)

    def process(self):
        """Call the handler's HTTP-method equivalent function and ALWAYS return Response"""

        method = self.request.method.upper()

        # Treat HEAD as GET for routing
        is_head = False
        if method == "HEAD":
            is_head = True
            method = "GET"

        if method == "PUT":
            # Create or update
            result = self.handler.save()
            # If save() returns nothing, a 204 is fine; otherwise pass content through
            if result in (None, b"", ""):
                return Response("", status=204)
            # Commonly XML for CRUD data
            mimetype = "application/xml" if (self.data_type == "data") else "text/plain"
            return self._wrap_response(result, default_mimetype=mimetype, status=200)

        if method == "GET":
            res = self.handler.read()
            # Decide content type
            if self.handler_type == ODOO_SERVICE_HANDLER:
                # ERP service responses are XML
                return self._wrap_response(res, default_mimetype="application/xml")
            if self.data_type == 'data':
                # Main form data is XML
                return self._wrap_response(res, default_mimetype="application/xml")
            # Fallback
            return self._wrap_response(res, default_mimetype="text/plain")

        if method == "POST":
            # Orbeon Search API (commonly XML payload/response)
            # If your search uses JSON instead, switch SEARCH_MIMETYPE to application/json
            criteria_bytes = self.data or b""
            # Optional: validate XML payload early to give clearer errors
            if SEARCH_MIMETYPE == "application/xml":
                try:
                    # Parse just to ensure well-formed; handlers can re-parse as needed
                    ET.fromstring(criteria_bytes or b"<empty/>")
                except ET.ParseError as e:
                    return Response(f"Invalid XML: {e}", status=400, mimetype="text/plain")

            res = self.handler.search()
            return self._wrap_response(res, default_mimetype=SEARCH_MIMETYPE)

        if method == "DELETE":
            # Implement if supported; otherwise 405
            if hasattr(self.handler, "delete"):
                res = self.handler.delete()
                if res in (None, b"", ""):
                    return Response("", status=204)
                # For deletes that return a body, default to text/plain
                return self._wrap_response(res, default_mimetype="text/plain")
            return Response("Method Not Allowed", status=405, mimetype="text/plain")

        # Anything else → 405
        return Response("Method Not Allowed", status=405, mimetype="text/plain")


class OrbeonPersistenceApp(object):
    def __init__(self, configfile_path=None):
        self.configfile_path = configfile_path

    def dispatch_request(self, request, wsgi_input=None):
        orbeon_request = OrbeonRequestHandler(request, self.configfile_path, wsgi_input)
        return orbeon_request.process()

    def wsgi_app(self, environ, start_response):
        request = Request(environ)
        _logger.debug("request: %s %s", request.method, request.path)

        response = self.dispatch_request(request, wsgi_input=environ.get('wsgi.input'))

        # Guard: always return a callable Response
        if not isinstance(response, Response):
            _logger.error("Invalid response type from process(): %r; coercing to 500", type(response))
            response = Response("Internal Server Error", status=500, mimetype="text/plain")

        # If the original request was HEAD, strip the body and enforce Content-Length: 0
        if request.method.upper() == "HEAD":
            # Drop any existing Content-Length and set to 0
            response.headers.pop("Content-Length", None)
            response.headers["Content-Length"] = "0"
            # Ensure the iterator yields no body
            response.set_data(b"")

        _logger.debug("response: %s", response.status)
        return response(environ, start_response)

    def __call__(self, environ, start_response):
        return self.wsgi_app(environ, start_response)


def create_app(configfile_path=None):
    return OrbeonPersistenceApp(configfile_path)
