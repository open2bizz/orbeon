# Copyright 2013-2021 Open2Bizz <info@open2bizz.nl>
# License LGPL-3

from odoo import api, fields, models, _

class ResPartner(models.Model):
    _inherit = 'res.users'

    api_key = fields.Char(help="Put your API key here to use orbeon for 2FA auth")
