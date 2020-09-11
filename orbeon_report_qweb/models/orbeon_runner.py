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
from odoo import fields, models, _, api, osv
from odoo.exceptions import UserError


import logging

_logger = logging.getLogger(__name__)


class OrbeonRunner(models.Model):
    _inherit = ['orbeon.runner']
    
    builder_reports_count = fields.Integer(
        compute='_builder_reports_count',
        string='Builder reports count'
    )

    
    def _builder_reports_count(self):
        self.builder_reports_count = len(self.builder_id.report_xml_ids)    

    
    def report_button(self, context=None):
        if self.builder_id.report_xml_ids:
            for report in self.builder_id.report_xml_ids:
                return self.env.ref(report.ir_actions_report_xml_id.report_name).report_action(self)
            
        else:
             raise UserError('There is no report linked to the Orbeon Builder Form of this Runner Form.')

                        

