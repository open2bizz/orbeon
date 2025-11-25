##### Copyright Open2Bizz 2025 #####

from odoo import models, fields, api


class OrbeonMaster(models.Model):
    _name = 'orbeon.master'
    _description = 'Orbeon Master Version'

    display_name = fields.Char("Name", compute="_set_name", store=True)
    master_builder_id = fields.Many2one('orbeon.builder', string="Master Builder")
    slave_ids = fields.One2many('orbeon.builder','master_id', string="Slave Builders")

    @api.depends('master_builder_id')
    def _set_name(self):
        for master in self:
            b_name = master.master_builder_id.complete_name or "Unknown"
            master.display_name = "Master " + "(" + b_name + ")"
