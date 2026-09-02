# -*- coding: utf-8 -*-
##############################################################################
# Copyright Open2Bizz 2025
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
from odoo.exceptions import ValidationError,UserError

from lxml import etree

import re

import logging
_logger = logging.getLogger(__name__)

STATE_CURRENT = 'current'
STATE_NEW = 'new'
STATE_OBSOLETE = 'obsolete'

class OrbeonBuilder(models.Model):
    _name = 'orbeon.builder'
    _inherit = ['mail.thread']
    _description = 'Orbeon Builder'
    _order = 'res_model_id DESC, name ASC, version ASC'

    name = fields.Char(
        "Name",
        required=True,
        help="""
        Identifies this specific form (e.g. "health-record" or "claim").
        This name can be used in APIs, so we recommend you use only lowercases characters.""",
    )

    display_name = fields.Char(
        "Full Name",
        compute='_compute_display_name',
        store=True
    )

    title = fields.Char(
        "Title",
        help="Form title in the current language",
        default="Untitled Form"
    )

    description = fields.Text(
        "Description",
        help="Form description in the current language")

    parent_id = fields.Many2one(
        'orbeon.builder',
        string='Parent Version',
        readonly=True
    )

    version = fields.Integer(
        "Version",
        required=True,
        readonly=True,
        default=1)

    version_comment = fields.Text(
        "Version Comment",
        required=True)

    state = fields.Selection(
        [
            (STATE_NEW, "New"),
            (STATE_CURRENT, "Current"),
            (STATE_OBSOLETE, "Obsolete"),
        ],
        "State",
        default=STATE_NEW,
        required=True,
        help="""\
        - New: In draft and was never published (Current)
        - Current: Published i.e. live
        - Obsolete: Was published but obsolete"""
    )

    xml = fields.Text(
        'XML')

    server_id = fields.Many2one(
        "orbeon.server",
        "Server",
        required=True,
        ondelete='restrict')

    builder_template_id = fields.Many2one(
        "orbeon.builder.template",
        "Builder Form Template",
        ondelete='set null',
        copy=False,
        help="By default some Builder Form Templates are shipped by the Orbeon Server."
    )

    runner_form_ids = fields.One2many(
        "orbeon.runner",
        "builder_id",
        string="Form runners")

    res_model_id = fields.Many2one(
        "ir.model",
        "Resource Model",
        help="Model as resource this form represents or acts on"
    )

    url = fields.Text(
        'URL',
        compute="_get_url",
        readonly=True)

    current_builder_id = fields.Many2one(
        "orbeon.builder",
        "Current Builder",
        compute="_current_builder",
        #store=True,
        help="The current (published) Builder"
    )

    debug_mode = fields.Boolean(
        'Debug Mode',
        default=False,
        help="Shows debug info (by field) in Orbeon Runner Form.\r\nAdds debug-info as messages (by field) on the Runner record."
    )

    master_id = fields.Many2one(
        "orbeon.master", string="Master Builder",
        help='This field links the first ever version of this builder and all the newly created builders.')

    @api.onchange('builder_template_id')
    def onchange_builder_template_id(self):
        for record in self:
            record.xml = record.builder_template_id.xml

    def init(self):
        if self.env['ir.model'].search([('model', '=', 'orbeon.master')]) and self.env['ir.model'].search(
                [('model', '=', 'orbeon.builder')]):
            for builder in self.env['orbeon.builder'].search([('parent_id', '=', False)]):
                master_record = self.env['orbeon.master'].search([('master_builder_id', '=', builder.id)])

                if not master_record:
                    master_record = self.env['orbeon.master'].create({'master_builder_id': builder.id})
                slave_ids = self.env['orbeon.builder'].search([('id', 'child_of', master_record.master_builder_id.id),
                                                               ('id', '!=', master_record.master_builder_id.id)])
                master_record.slave_ids = [(6, 0, slave_ids.ids)]

    @api.depends('title', 'name', 'version')
    def _compute_display_name(self):
        for record in self:
            record.display_name = " ".join([record.title or "", record.name or "", "(", str(record.version or ""), ")"])

    @api.constrains('name')
    def constaint_check_name(self):
        if re.search(r"[^a-zA-Z0-9_-]", self.name) is not None:
            raise ValidationError('Name is invalid. Use ASCII letters, digits, "-" or "_"')

    @api.constrains("name", "state")
    def constraint_one_current(self):
        """Per name there can be only 1 record with
        state current at a time.
        """
        cur_record = self.search([
            ("name", "=", self.name),
            ("state", "=", STATE_CURRENT)
        ])
        if len(cur_record) > 1:
            raise ValidationError("%s already has a record with status 'current'.\
                    Only one builder form can be current at a time." % self.name)

    @api.constrains("name", "version")
    def constraint_one_version(self):
        """Per name there can be only 1 record with
        same version at a time.
        """

        domain = [('name', '=', self.name)]
        name_version_grouped = self.read_group(domain, ['version'], ['version'])

        if name_version_grouped[0]['version_count'] > 1:
            raise ValidationError("%s already has a record with version: %d"
                                  % (self.name, self.version))

    def validate_create_xml(self, vals):
        _logger.debug(vals)
        for rec in vals:
            if rec['builder_template_id'] and rec['xml']:
                raise ValidationError("Provide either a \"Builder Form Template\" or XML. Both not allowed.")

            if not rec['builder_template_id'] and not rec['xml']:
                raise ValidationError("Missing either a \"Builder Form Template\" or XML")


    @api.returns('self', lambda value: value)
    def copy_as_new_version(self):
        """Get last version for builder-forms by traversing-up on parent_id"""

        builder = self

        while builder.parent_id:
            builder = builder.parent_id

        builder = self.search([('id', 'child_of', builder.id)], limit=1, order='id DESC')

        alter = {}
        alter["parent_id"] = self.id
        alter["state"] = STATE_NEW
        alter["version"] = builder.version + 1
        alter["builder_template_id"] = False

        res = super(OrbeonBuilder, self).copy(alter)

        return res

    def new_version_builder_form(self):
        res = self.copy_as_new_version()

        form_view = self.env["ir.ui.view"].search(
            [("name", "=", "orbeon.builder_form.form")]
        )[0]

        tree_view = self.env["ir.ui.view"].search(
            [("name", "=", "orbeon.builder_form.tree")]
        )[0]

        return {
            "name": self.name,
            "type": "ir.actions.act_window",
            "res_model": "orbeon.builder",
            "view_mode": "form, list",
            "views": [
                [form_view.id, "form"],
                [tree_view.id, "list"],
            ],
            "target": "current",
            "res_id": res.id,
            "context": {}
        }

    def open_orbeon_builder_form(self):
        return {
            "name": 'Orbeon',
            "type": "ir.actions.act_url",
            "target": "new",
            'url': self.url
        }

    def _get_url(self):
        self.ensure_one()
        if isinstance(self.id, models.NewId):
            return {}

        if hasattr(self, '_origin') and not isinstance(self._origin.id, models.NewId):
            builder_id = self._origin.id
        else:
            builder_id = self.id

        builder_url = "/orbeon/%s" % ("fr/orbeon/builder")
        get_mode = {STATE_NEW: 'edit'}
        url = "%s/%s/%i" % (builder_url, get_mode.get(self.state, 'view'), builder_id)

        self.url = url

    @api.depends('master_id', 'state', 'master_id.slave_ids')
    def _current_builder(self):
        for record in self:
            if record.master_id:
                builder = self.env['orbeon.builder'].search(
                    [('master_id','=', record.master_id.id),('state', '=', 'current')],
                    order='id desc', limit=1) or False
            record.current_builder_id = builder.id if builder else False

    @api.model
    def orbeon_search_read_data(self, domain=None, fields=None):
        builder = self.search(domain or [], limit=1)

        res = {'id': builder['id']}

        for f in fields:
            res[f] = builder[f]

        return res

    def get_xml_form_node(self):
        parser = etree.XMLParser(ns_clean=True, encoding='utf-8')

        # Cast to string, to prevent Unicode error!
        root = etree.XML(self.xml.encode('utf-8'), parser)
        form_node = root.xpath(
            "//xf:instance[@id='fr-form-instance']/form",
            namespaces={'xf': "http://www.w3.org/2002/xforms"}
        )[0]
        form = etree.XML(etree.tostring(form_node, encoding='unicode'), parser)
        etree.cleanup_namespaces(form)

        return etree.tostring(form, encoding='unicode')

    def action_pretty_print_xml(self):
        """ Pretty prints the XML field using lxml """
        for record in self:
            if not record.xml:
                continue
            try:
                parser = etree.XMLParser(remove_blank_text=True)
                node = etree.fromstring(record.xml.encode('utf-8'), parser)
                record.xml = etree.tostring(node, pretty_print=True, encoding='unicode')
            except Exception as e:
                _logger.debug("Failed to pretty print XML: %s", str(e))
                raise UserError(_("Invalid XML format: %s") % str(e))

    def view_runner_forms(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("orbeon.orbeon_runner_form_action")
        action['domain'] = [
            ('builder_id', '=', self.id)
        ]
        action['context'] = {'default_builder_id': self.id}
        return action
