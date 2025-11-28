# -*- coding: utf-8 -*-
##############################################################################
#
#    Copyright Open2Bizz 2025
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
    "name": "Orbeon Forms on Projects",
    'summary': 'Orbeon Forms on Projects',
    "version": "18.0.1.0.0",
    "author": "Open2bizz",
    "website": "http://www.open2bizz.nl",
    "license": "LGPL-3",
    "category": "Project",
    "depends": [
        "project",
        "orbeon",
    ],
    "data": [
        "security/res_groups.xml",
        "security/ir.model.access.csv",
        "views/orbeon_runner.xml",
        "views/project.xml",
        "data/orbeon_project_data.xml",
        "data/orbeon_template.xml",
    ],
    "application": True,
    "installable": True,
}
