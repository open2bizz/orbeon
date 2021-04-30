# -*- coding: utf-8 -*-
##############################################################################
#
#    open2bizz
#    Copyright (C) 2017 open2bizz (open2bizz.nl).
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
from odoo import fields, models

import logging

_logger = logging.getLogger(__name__)


class OrbeonBuilder(models.Model):
    _name = 'orbeon.builder'
    _inherit = ['orbeon.builder']

    report_xml_ids = fields.One2many(
        'orbeon.builder.report.xml',
        "orbeon_builder_id",
        string="Reports"
    )

    def new_version_builder_form(self):
        res = super(OrbeonBuilder, self).new_version_builder_form()

        report_name = "%s %s" %(self.title, (self.version + 1))
        tech_report_name = "orbeon_qweb.%s_%s" %(self.title, (self.version + 1))

        new_report = self.env['ir.actions.report'].create({
            'name' : report_name,
            'report_type' : 'qweb-pdf',
            'model' : 'orbeon.runner',
            'report_name' : tech_report_name
        })

        new_report_line = self.env['orbeon.builder.report.xml'].create({
            'orbeon_builder_id' : res['res_id'],
            'ir_actions_report_xml_id' : new_report.id
        })

        return res