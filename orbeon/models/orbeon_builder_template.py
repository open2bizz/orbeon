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
        required=False,
        ondelete='cascade'
    )

    module_id = fields.Many2one(
        "ir.module.module",
        "Module",
        required=False,
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

    @api.depends('server_id', 'module_id', 'form_name')
    def _set_name(self):
        self.name = "%s (%s)" % (self.form_name, self.module_id.name)

    
    @api.constrains('form_name')
    def constaint_check_name(self):
        if re.search(r"[^a-zA-Z0-9_-]", self.form_name) is not None:
            raise ValidationError('Name is invalid. Use ASCII letters, digits, "-" or "_"')
