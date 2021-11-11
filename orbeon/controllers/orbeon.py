# -*- coding: utf-8 -*-
##############################################################################
# Author: Open2Bizz (www.open2bizz.nl)
# Employee: Dennis Ochse
# Date: 2019-05-02
#
# GNU LESSER GENERAL PUBLIC LICENSE
# Version 3, 29 June 2007
#
# Copyright (C) 2007 Free Software Foundation, Inc. <https://fsf.org/>
# Everyone is permitted to copy and distribute verbatim copies
# of this license document, but changing it is not allowed.
#
#
# This version of the GNU Lesser General Public License incorporates
# the terms and conditions of version 3 of the GNU General Public
# License, supplemented by the additional permissions listed in the following URL:
# https://www.gnu.org/licenses/lgpl.txt.
#
##############################################################################
import requests
from urllib.parse import urlparse
from werkzeug.wrappers import Response
from odoo import http
import base64
from odoo.tools import config

import logging

_logger = logging.getLogger(__name__)


class Orbeon(http.Controller):
    orbeon_base_route = 'orbeon'

    @http.route('/%s/<path:path>' % orbeon_base_route, type='http', auth="user", csrf=False)
    def render_orbeon_page(self, path, redirect=None, **kw):
        orbeon_server = http.request.env["orbeon.server"].search_read([], ['url'])
        if len(orbeon_server) == 0:
            return 'Orbeon server not found'
        else:
            orbeon_server = orbeon_server[0]
        o = urlparse(orbeon_server['url'])
        _logger.error(o)

        odoo_session = http.request.session

        orbeon_headers = ['cookie']
        in_headers = {name: value for (name, value) in http.request.httprequest.headers.items()
                      if name.lower() in orbeon_headers}

        in_headers.update({'Openerp-Server': 'localhost'})
        in_headers.update({'Openerp-Port': str(config.get('xmlrpc_port_orbeon'))})
        in_headers.update({'Openerp-Database': odoo_session.get('db')})
        _logger.error(odoo_session)
        x = base64.b64encode(bytes(odoo_session.get('login'), 'utf-8'))
        y = base64.b64encode(bytes(odoo_session.get('password'), 'utf-8'))
        in_headers.update({'Authorization': 'Basic %s' % (x.decode('utf-8') + ':' + y.decode('utf-8'))})
        _logger.debug('Calling Orbeon on url %s with header %s' % (o.netloc, in_headers))
        curl = urlparse(http.request.httprequest.url)._replace(netloc=o.netloc, scheme='http')
        _logger.error(curl)
        resp = requests.request(
            method=http.request.httprequest.method,
            url=curl.geturl(),
            headers=in_headers,
            data=http.request.httprequest.form if len(
                http.request.httprequest.form) > 0 else http.request.httprequest.get_data(),
            # cookies=http.request.httprequest.cookies,
            allow_redirects=False)
        _logger.error(resp)
        excluded_headers = ['content-encoding', 'content-length', 'transfer-encoding', 'connection'
            , 'openerp-server', 'openerp-port', 'openerp-database', 'authorization']
        headers = [(name, value) for (name, value) in resp.raw.headers.items()
                   if name.lower() not in excluded_headers]

        response = Response(resp.content, resp.status_code, headers)
        return response
