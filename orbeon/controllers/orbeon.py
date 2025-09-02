# -*- coding: utf-8 -*-
##############################################################################
# Copyright Open2Bizz 2025
#
# GNU LESSER GENERAL PUBLIC LICENSE
# Version 3, 29 June 2007
#
# https://www.gnu.org/licenses/lgpl.txt
#
##############################################################################

import base64
import logging
from urllib.parse import urlparse

import requests
from odoo import http
from odoo.http import Response as HttpResponse
from odoo.tools import config

_logger = logging.getLogger(__name__)


class Orbeon(http.Controller):
    orbeon_base_route = "orbeon"

    @http.route("/%s/<path:path>" % orbeon_base_route, type="http", auth="user", csrf=False)
    def render_orbeon_page(self, path, redirect=None, **kw):
        # Find Orbeon server URL
        orbeon_server = http.request.env["orbeon.server"].search_read([], ["url"])
        if not orbeon_server:
            return "Orbeon server not found"
        orbeon_server = orbeon_server[0]

        o = urlparse(orbeon_server["url"])
        _logger.debug("___Orbeon Server URL___ %s", o)

        # Build outbound request URL: keep path/query, replace scheme+netloc
        incoming = urlparse(http.request.httprequest.url)
        curl = incoming._replace(netloc=o.netloc, scheme="http")
        target_url = curl.geturl()
        _logger.debug("___Curl___ %s", curl)

        # Forward selected inbound headers
        req = http.request.httprequest
        odoo_session = http.request.session

        in_headers = {
            name: value
            for (name, value) in req.headers.items()
            if name.lower() in {"cookie"}
        }

        # Custom headers for Orbeon
        in_headers.update({
            "Openerp-Server": "localhost",
            "Openerp-Port": str(config.get("xmlrpc_port_orbeon")),
            "Openerp-Database": odoo_session.get("db"),
        })

        # Proper HTTP Basic Authorization: base64("user:password")
        user = odoo_session.get("login") or ""
        pw = str(config.get("orbeon_password") or "")
        basic_token = base64.b64encode(f"{user}:{pw}".encode("utf-8")).decode("utf-8")
        in_headers["Authorization"] = f"Basic {basic_token}"

        _logger.debug("Calling Orbeon on url %s with headers %s", target_url, in_headers)

        # Choose body: form (dict-like) or raw bytes
        data = req.form if req.form else req.get_data()

        # Make proxied request
        resp = requests.request(
            method=req.method,
            url=target_url,
            headers=in_headers,
            data=data,
            allow_redirects=False,
        )
        _logger.debug("___Request___ status=%s headers=%s", resp.status_code, dict(resp.headers))

        # Filter hop-by-hop/problematic headers before returning to Odoo/Werkzeug
        HOP_BY_HOP = {
            "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
            "te", "trailers", "transfer-encoding", "upgrade",
            "content-encoding", "content-length",
            # custom headers we injected on the way in:
            "openerp-server", "openerp-port", "openerp-database", "authorization",
        }
        proxied_headers = [(k, v) for k, v in resp.headers.items() if k.lower() not in HOP_BY_HOP]

        # Build Odoo HTTP response
        return HttpResponse(
            resp.content,
            status=resp.status_code,
            headers=proxied_headers,
            content_type=resp.headers.get("Content-Type"),
        )
