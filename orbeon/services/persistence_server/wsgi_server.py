# -*- coding: utf-8 -*-
##############################################################################
# Author: Open2Bizz (www.open2bizz.nl)
# Employee: Dennis Ochse
# Date: 2019-05-02 (updated 2025-09-02)
#
# GNU LESSER GENERAL PUBLIC LICENSE v3
##############################################################################
import base64
import logging
from xml.etree import ElementTree as ET

from werkzeug.wrappers import Request, Response
from werkzeug.exceptions import InternalServerError

# NOTE: make sure your orbeon_handlers.py defines FormMetadataHandler
from .orbeon_handlers import (
    BuilderHandler,
    RunnerHandler,
    OdooServiceHandler,
    FormMetadataHandler,  # NEW
)
from .. import utils
from odoo.tools import config

_logger = logging.getLogger(__name__)
_log = utils._log

BUILDER_HANDLER = 'builder_handler'
RUNNER_HANDLER = 'runner_handler'
ODOO_SERVICE_HANDLER = 'odoo_service_handler'
FORM_METADATA_HANDLER = 'form_metadata_handler'  # NEW

SEARCH_MIMETYPE = "application/xml"   # Adjust to "application/json" if your handler/search returns JSON.


class OrbeonRequestHandler(object):
    """Orbeon (HTTP) request handler"""

    def __init__(self, request, configfile_path=None, wsgi_input=None):
        _logger.debug("OrbeonRequestHandler.__init__: ENTER request=%r path=%s",
                      getattr(request, "method", None), getattr(request, "path", None))
        # Prefer explicit path from caller; fall back to standard Odoo path
        configfile_path = configfile_path or '/etc/odoo-server.conf'
        _log("debug", "configfile_path => %s" % configfile_path)
        _logger.debug("OrbeonRequestHandler.__init__: using configfile_path=%s", configfile_path)

        self.request = request

        # --- Normalize Orbeon 2024 persistence prefixes so our router sees /crud|/search|/erp|/form ---
        raw_path = request.path or "/"
        self._is_persistence = False
        for pref in ("/fr/service/persistence", "/orbeon/fr/service/persistence"):
            if raw_path.startswith(pref + "/") or raw_path == pref:
                self._is_persistence = True
                raw_path = raw_path[len(pref):]  # keep the leading slash of the remainder
                break
        normalized = raw_path if raw_path.startswith("/") else "/" + raw_path
        self.path = normalized.split("/")

        self.args = request.args
        _logger.debug("OrbeonRequestHandler.__init__: raw path=%s normalized=%s split=%s args=%s persistence=%s",
                      request.path, normalized, self.path, dict(self.args or {}), self._is_persistence)

        # Handle body (including old chunked quirk)
        try:
            if request.headers.get('Transfer-Encoding', '') == 'chunked' and request.headers.get('Content-Length', ' ') != ' ':
                _logger.debug("OrbeonRequestHandler.__init__: handling chunked request body")
                body = b''
                if wsgi_input is not None:
                    size_line = wsgi_input.readline()
                    try:
                        size = int(size_line, 16)
                    except Exception as e:
                        _logger.debug("OrbeonRequestHandler.__init__: chunked size parse error=%s line=%r", e, size_line)
                        size = 0
                    while size > 0:
                        body += wsgi_input.read(size + 2)[:-2]
                        try:
                            size = int(wsgi_input.readline(), 16)
                        except Exception as e:
                            _logger.debug("OrbeonRequestHandler.__init__: chunked size loop parse error=%s", e)
                            size = 0
                self.data = body
                _logger.debug("OrbeonRequestHandler.__init__: chunked body length=%d", len(self.data or b""))
            else:
                self.data = request.data
                _logger.debug("OrbeonRequestHandler.__init__: non-chunked body length=%d", len(self.data or b""))
        except Exception as e:
            _logger.debug("OrbeonRequestHandler.__init__: ERROR reading body: %s", e, exc_info=True)
            self.data = b""

        # Parsed attrs from the (normalized) path
        self.namespace = None
        self.app = None
        self.form = None
        self.data_type = None
        self.set_path_attrs()

        # Select handler type and instance
        self.handler_type = None
        self.set_handler_type()

        self.handler = None
        self.set_handler()

        # Configure backends ONLY if we actually have a handler needing XML-RPC
        try:
            if self.handler is None:
                _logger.debug("OrbeonRequestHandler.__init__: no handler for namespace=%s; skip backend config", self.namespace)
            elif self.handler_type in (BUILDER_HANDLER, RUNNER_HANDLER, ODOO_SERVICE_HANDLER):
                if configfile_path is not None:
                    _logger.debug("OrbeonRequestHandler.__init__: set_config_by_file_path(%s)", configfile_path)
                    self.handler.set_config_by_file_path(configfile_path)

                if getattr(self.handler, "config", None) is not None and len(self.handler.config.sections()) > 0:
                    _logger.debug("OrbeonRequestHandler.__init__: using XML-RPC from config (sections=%d)", len(self.handler.config.sections()))
                    self.handler.set_xmlrpc_by_config(request)
                else:
                    _logger.debug("OrbeonRequestHandler.__init__: building XML-RPC from headers")
                    url = "http://%s:%s" % (
                        request.headers.get("Openerp-Server"),
                        request.headers.get("Openerp-Port"),
                    )
                    db = request.headers.get("Openerp-Database")
                    _logger.debug("OrbeonRequestHandler.__init__: xmlrpc url=%s db=%s", url, db)

                    # Preferred: credentials from Odoo config
                    usr = str(config.get("orbeon_user"))
                    passwd = str(config.get("orbeon_password"))
                    _logger.debug("OrbeonRequestHandler.__init__: credentials source=odoo.config has_user=%s has_password=%s",
                                  bool(usr), bool(passwd))

                    # Optional: honor Basic Authorization header if present
                    auth_hdr = request.headers.get("Authorization")
                    if auth_hdr and auth_hdr.startswith("Basic "):
                        _logger.debug("OrbeonRequestHandler.__init__: Authorization header present; attempting decode of username only")
                        try:
                            decoded = base64.b64decode(auth_hdr.split(" ", 1)[1]).decode("utf-8")
                            # Format is "user:pass"
                            u, p = decoded.split(":", 1)
                            usr = u or usr
                            # DO NOT log password
                            if p:
                                passwd = p
                            _logger.debug("OrbeonRequestHandler.__init__: Authorization username resolved user=%s (password masked)", usr)
                        except Exception as e:
                            _logger.debug("OrbeonRequestHandler.__init__: Authorization decode error: %s", e, exc_info=True)

                    # NEVER log credentials content
                    self.handler.set_xmlrpc(db, usr, passwd, url)
                    _logger.debug("OrbeonRequestHandler.__init__: set_xmlrpc completed")
            else:
                _logger.debug("OrbeonRequestHandler.__init__: handler doesn't require XML-RPC (type=%s)", self.handler_type)
        except Exception as e:
            _logger.debug("OrbeonRequestHandler.__init__: ERROR configuring XML-RPC: %s", e, exc_info=True)
        _logger.debug("OrbeonRequestHandler.__init__: EXIT")

    def set_path_attrs(self):
        """Set Request path-components to object attributes following:
           https://doc.orbeon.com/form-runner/api/persistence
           Expect: /{namespace}/{app}/{form}/{data_type}/...
        """
        _logger.debug("set_path_attrs: ENTER with path=%s", self.path)
        try:
            # path[0] is '', because leading slash
            if len(self.path) > 1:
                self.namespace = self.path[1]
            if len(self.path) > 2:
                self.app = self.path[2]
            if len(self.path) > 3:
                self.form = self.path[3]
            if len(self.path) > 4:
                self.data_type = self.path[4]
            _logger.debug("set_path_attrs: namespace=%s app=%s form=%s data_type=%s",
                          self.namespace, self.app, self.form, self.data_type)
        except Exception as e:
            _logger.debug("set_path_attrs: ERROR parsing path components: %s", e, exc_info=True)
        _logger.debug("set_path_attrs: EXIT")

    def set_handler_type(self):
        """Get Orbeon handler type (class)"""
        _logger.debug("set_handler_type: ENTER namespace=%s app=%s form=%s persistence_pref=%s",
                      self.namespace, self.app, self.form, self._is_persistence)
        try:
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
            # /form/... ONLY when coming via persistence prefix -> Forms Metadata API (v1)
            elif self.namespace == 'form' and self._is_persistence:
                self.handler_type = FORM_METADATA_HANDLER
            elif self.namespace == 'form':
                # Handle Forms Metadata API whether or not a persistence prefix was present
                self.handler_type = FORM_METADATA_HANDLER
            else:
                self.handler_type = None
            _logger.debug("set_handler_type: resolved handler_type=%s", self.handler_type)
        except Exception as e:
            _logger.debug("set_handler_type: ERROR resolving handler type: %s", e, exc_info=True)
        _logger.debug("set_handler_type: EXIT")

    def set_handler(self):
        """Instantiate the proper handler based on handler_type"""
        _logger.debug("set_handler: ENTER handler_type=%s", self.handler_type)
        try:
            if self.handler_type == BUILDER_HANDLER:
                self.handler = BuilderHandler(self.app, self.form, self.data_type, self.path, self.args, self.data)
            elif self.handler_type == RUNNER_HANDLER:
                self.handler = RunnerHandler(self.app, self.form, self.data_type, self.path, self.args, self.data)
            elif self.handler_type == ODOO_SERVICE_HANDLER:
                self.handler = OdooServiceHandler(self.app, self.form, self.data_type, self.path, self.args, self.data)
            elif self.handler_type == FORM_METADATA_HANDLER:
                self.handler = FormMetadataHandler(self.app, self.form, self.data_type, self.path, self.args, self.data)
                # Pass headers so handler can read Orbeon-Form-Definition-Version if present
                try:
                    self.handler.request_headers = dict(self.request.headers or {})
                except Exception:
                    pass
            else:
                _logger.debug("set_handler: No handler for namespace=%s app=%s form=%s data_type=%s -> None",
                              self.namespace, self.app, self.form, self.data_type)
                self.handler = None
            _logger.debug("set_handler: instantiated handler=%r",
                          (type(self.handler).__name__ if self.handler else None))
        except Exception as e:
            _logger.debug("set_handler: ERROR instantiating handler: %s", e, exc_info=True)
            raise
        _logger.debug("set_handler: EXIT")

    def _wrap_response(self, payload, default_mimetype="text/plain", status=200):
        """Normalize handler outputs into a Werkzeug Response."""
        _logger.debug("_wrap_response: ENTER status=%s default_mimetype=%s payload_type=%s",
                      status, default_mimetype, type(payload).__name__)
        try:
            if isinstance(payload, Response):
                _logger.debug("_wrap_response: payload already Response; EXIT")
                return payload
            if payload is None:
                payload = ""  # Avoid NoneType downstream
            resp = Response(payload, status=status, mimetype=default_mimetype)
            _logger.debug("_wrap_response: created Response len=%s", len(payload) if hasattr(payload, "__len__") else "n/a")
            return resp
        except Exception as e:
            _logger.debug("_wrap_response: ERROR creating response: %s", e, exc_info=True)
            return Response("Internal Server Error", status=500, mimetype="text/plain")

    def process(self):
        """Call the handler's HTTP-method equivalent function and ALWAYS return Response"""
        _logger.debug("process: ENTER method=%s path=%s args=%s",
                      self.request.method.upper(), self.request.path, dict(self.args or {}))

        # No handler mapped (e.g., non-persistence /form or unknown) -> 404
        if getattr(self, "handler", None) is None:
            _logger.debug("process: No handler mapped for this namespace; returning 404")
            return Response("Not Found", status=404, mimetype="text/plain")

        method = self.request.method.upper()

        # Treat HEAD as GET for routing; body stripped later by wsgi_app
        is_head = False
        if method == "HEAD":
            _logger.debug("process: HEAD detected; routing as GET and stripping body later")
            is_head = True
            method = "GET"

        try:
            if method == "PUT":
                _logger.debug("process: PUT -> handler.save()")
                result = self.handler.save()
                _logger.debug("process: PUT save() result type=%s len=%s", type(result).__name__, (len(result) if result else 0))
                if result in (None, b"", ""):
                    _logger.debug("process: PUT returning 204 No Content")
                    return Response("", status=204)
                mimetype = "application/xml" if (self.data_type == "data") else "text/plain"
                _logger.debug("process: PUT returning 200 with mimetype=%s", mimetype)
                return self._wrap_response(result, default_mimetype=mimetype, status=200)

            if method == "GET":
                _logger.debug("process: GET -> handler.read()")
                res = self.handler.read()

                # If handler returned a Response, just pass it through (don't call len())
                if isinstance(res, Response):
                    _logger.debug("process: GET handler returned Response; passthrough status=%s mimetype=%s",
                                  getattr(res, "status", None), getattr(res, "mimetype", None))
                    return res

                # Only now is it safe to log length
                try:
                    res_len = len(res) if res is not None and hasattr(res, "__len__") else 0
                except Exception:
                    res_len = 0
                _logger.debug("process: GET read() result type=%s len=%s", type(res).__name__, res_len)

                # Decide content type
                if self.handler_type == ODOO_SERVICE_HANDLER:
                    _logger.debug("process: GET returning application/xml for ODOO_SERVICE_HANDLER")
                    return self._wrap_response(res, default_mimetype="application/xml")
                if self.data_type == 'data':
                    _logger.debug("process: GET returning application/xml for data_type=data")
                    return self._wrap_response(res, default_mimetype="application/xml")
                if self.data_type == 'form':
                    _logger.debug("process: GET returning application/xhtml+xml for data_type=form")
                    return self._wrap_response(res, default_mimetype="application/xhtml+xml")
                # Fallback
                _logger.debug("process: GET returning text/plain fallback")
                return self._wrap_response(res, default_mimetype="text/plain")

            if method == "POST":
                _logger.debug("process: POST -> handler.search() with SEARCH_MIMETYPE=%s", SEARCH_MIMETYPE)
                criteria_bytes = self.data or b""
                _logger.debug("process: POST payload length=%d", len(criteria_bytes))
                if SEARCH_MIMETYPE == "application/xml":
                    try:
                        ET.fromstring(criteria_bytes or b"<empty/>")
                        _logger.debug("process: POST XML payload well-formed")
                    except ET.ParseError as e:
                        _logger.debug("process: POST Invalid XML: %s", e, exc_info=True)
                        return Response(f"Invalid XML: {e}", status=400, mimetype="text/plain")
                res = self.handler.search()
                _logger.debug("process: POST search() result type=%s len=%s", type(res).__name__, (len(res) if res else 0))
                return self._wrap_response(res, default_mimetype=SEARCH_MIMETYPE)

            if method == "DELETE":
                _logger.debug("process: DELETE")
                if hasattr(self.handler, "delete"):
                    _logger.debug("process: DELETE -> handler.delete()")
                    res = self.handler.delete()
                    _logger.debug("process: DELETE result type=%s len=%s", type(res).__name__, (len(res) if res else 0))
                    if res in (None, b"", ""):
                        _logger.debug("process: DELETE returning 204 No Content")
                        return Response("", status=204)
                    _logger.debug("process: DELETE returning 200 text/plain")
                    return self._wrap_response(res, default_mimetype="text/plain")
                _logger.debug("process: DELETE not supported -> 405")
                return Response("Method Not Allowed", status=405, mimetype="text/plain")

            _logger.debug("process: unsupported method=%s -> 405", method)
            return Response("Method Not Allowed", status=405, mimetype="text/plain")
        except Exception as e:
            _logger.debug("process: ERROR handling method=%s: %s", method, e, exc_info=True)
            return Response("Internal Server Error", status=500, mimetype="text/plain")
        finally:
            _logger.debug("process: EXIT")


class OrbeonPersistenceApp(object):
    def __init__(self, configfile_path=None):
        _logger.debug("OrbeonPersistenceApp.__init__: ENTER configfile_path=%s", configfile_path)
        self.configfile_path = configfile_path
        _logger.debug("OrbeonPersistenceApp.__init__: EXIT")

    def dispatch_request(self, request, wsgi_input=None):
        _logger.debug("dispatch_request: ENTER method=%s path=%s", request.method, request.path)
        try:
            orbeon_request = OrbeonRequestHandler(request, self.configfile_path, wsgi_input)
            resp = orbeon_request.process()
            _logger.debug("dispatch_request: got Response status=%s", getattr(resp, "status", None))
            return resp
        except Exception as e:
            _logger.debug("dispatch_request: ERROR %s", e, exc_info=True)
            return Response("Internal Server Error", status=500, mimetype="text/plain")
        finally:
            _logger.debug("dispatch_request: EXIT")

    def wsgi_app(self, environ, start_response):
        _logger.debug("wsgi_app: ENTER environ PATH_INFO=%s REQUEST_METHOD=%s", environ.get("PATH_INFO"), environ.get("REQUEST_METHOD"))
        try:
            request = Request(environ)
            _logger.debug("request: %s %s", request.method, request.path)
            _logger.debug("wsgi_app: constructed Request method=%s path=%s headers_keys=%s",
                          request.method, request.path, list(request.headers.keys())[:10])

            response = self.dispatch_request(request, wsgi_input=environ.get('wsgi.input'))

            # Guard: always return a callable Response
            if not isinstance(response, Response):
                _logger.debug("wsgi_app: Invalid response type from process(): %r; coercing to 500", type(response))
                response = Response("Internal Server Error", status=500, mimetype="text/plain")

            # If the original request was HEAD, strip the body and enforce Content-Length: 0
            if request.method.upper() == "HEAD":
                _logger.debug("wsgi_app: HEAD request -> strip body & set Content-Length: 0")
                response.headers.pop("Content-Length", None)
                response.headers["Content-Length"] = "0"
                response.set_data(b"")

            _logger.debug("response: %s", response.status)
            _logger.debug("wsgi_app: EXIT status=%s", response.status)
            return response(environ, start_response)
        except Exception as e:
            _logger.debug("wsgi_app: ERROR %s", e, exc_info=True)
            resp = Response("Internal Server Error", status=500, mimetype="text/plain")
            return resp(environ, start_response)

    def __call__(self, environ, start_response):
        _logger.debug("__call__: delegating to wsgi_app")
        return self.wsgi_app(environ, start_response)


def create_app(configfile_path=None):
    _logger.debug("create_app: ENTER configfile_path=%s", configfile_path)
    app = OrbeonPersistenceApp(configfile_path)
    _logger.debug("create_app: EXIT returning OrbeonPersistenceApp")
    return app
