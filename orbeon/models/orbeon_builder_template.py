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
from odoo import models, fields, api
from odoo.exceptions import ValidationError

import re

import logging
_logger = logging.getLogger(__name__)


class OrbeonBuilderTemplate(models.Model):
    _name = 'orbeon.builder.template'
    _inherit = ['mail.thread']
    _description = 'Orbeon Builder Template'

    _rec_name = "name"

    name = fields.Char(
        "Name",
        compute="_set_name",
        store=True,
        readonly=True
    )

    server_id = fields.Many2one(
        "orbeon.server",
        "Server",
        ondelete='cascade'
    )

    module_id = fields.Many2one(
        "ir.module.module",
        "Module",
        readonly=True,
        ondelete='cascade'
    )

    form_name = fields.Char(
        "Form Name",
        required=True
    )

    xml = fields.Text(
        'XML'
    )

    fetched_from_orbeon = fields.Boolean(
        "Fetched from Orbeon",
        default=False,
        help="Template was fetched from Orbeon"
    )

    @api.multi
    @api.depends('server_id', 'module_id', 'form_name')
    def _set_name(self):
        for rec in self:
            rec.name = "%s (%s)" % (rec.form_name, rec.module_id.name)

    @api.multi
    @api.constrains('form_name')
    def constaint_check_name(self):
        for name in self.mapped('form_name'):
            if re.search(r"[^a-zA-Z0-9_-]", name) is not None:
                raise ValidationError('Name is invalid. Use ASCII letters, digits, "-" or "_"')
