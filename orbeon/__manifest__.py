# -*- coding: utf-8 -*-
##############################################################################
#
#    open2bizz
#    Copyright (C) 2016 open2bizz (open2bizz.nl).
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

{
    "name": "Orbeon Forms",
    "summary": 'Integrate Orbeon Forms with Odoo',
    "description": 'Orbeon Forms integration',
    "version": "14.0.2",
    "author": "Open2bizz",
    "website": "http://www.open2bizz.nl",
    "license": "LGPL-3",
    "category": "Extra Tools",
    "depends": ['base', 'mail'],
    'external_dependencies': {
        'python': ['dicttoxml', 'xmlunittest']
    },
    "data": [
        "security/res_groups.xml",
        "security/ir_model_access.xml",
        "views/orbeon_builder_template.xml",
        "views/orbeon_builder.xml",
        "views/orbeon_runner.xml",
        "views/orbeon_server.xml",
        "views/base.xml",
        "views/res_users.xml",
        "data/orbeon_builder_template_empty.xml"
    ],
    'demo': [
        'data/demo_data.xml',
    ],
    "application": True,
    "installable": True,
}
