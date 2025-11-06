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
from odoo.exceptions import ValidationError, UserError

from lxml import etree

import re

import logging

_logger = logging.getLogger(__name__)

STATE_CURRENT = 'current'
STATE_NEW = 'new'
STATE_OBSOLETE = 'obsolete'


class OrbeonBuilder(models.Model):
    _name = 'orbeon.master'
    _description = 'Orbeon Master Version'

    master_builder_id = fields.Many2one('orbeon.builder', string="Master Builder")
    slave_ids = fields.One2many('orbeon.builder', 'master_id', string="Slave Builders")
    display_name = fields.Char("Name", compute="_set_name")

    def _set_name(self):
        for master in self:
            b_name = master.master_builder_id.complete_name or "Unknown"
            master.display_name = "Master " + "(" + b_name + ")"


class OrbeonBuilder(models.Model):
    _name = 'orbeon.builder'
    _inherit = ['mail.thread']
    _description = 'Orbeon Builder'

    _order = 'res_model_id DESC, name ASC, version ASC'
    _rec_name = 'complete_name'

    name = fields.Char(
        "Name",
        required=True,
        help="""
        Identifies this specific form (e.g. "health-record" or "claim").
        This name can be used in APIs, so we recommend you use only lowercases characters.""",
    )

    title = fields.Char(
        "Title",
        help="Form title in the current language",
        default="Untitled Form"
    )

    description = fields.Text(
        "Description",
        help="Form description in the current language")

    complete_name = fields.Char(
        "Full Name",
        compute='_compute_complete_name',
        store=True
    )

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
        help="The current (published) Builder"
    )

    debug_mode = fields.Boolean(
        'Debug Mode',
        default=False,
        help="Shows debug info (by field) in Orbeon Runner Form.\r\nAdds debug-info as messages (by field) on the Runner record."
    )

    master_id = fields.Many2one("orbeon.master", string="Master Builder",
                                help='This field links the first ever version of this builder will all the newly created builders.')

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
    def _compute_complete_name(self):
        for record in self:
            record.complete_name = "%s (%s @ %s @ %s)" % (record.title, record.name, record.state, record.version)

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

    from lxml import etree
    from odoo import api, models
    from odoo.exceptions import ValidationError
    import logging

    _logger = logging.getLogger(__name__)

    class OrbeonBuilder(models.Model):
        _name = "orbeon.builder"

        # ... your fields here ...

        @api.model_create_multi
        def create(self, vals_list):
            _logger.error("create called; #records=%s", len(vals_list))
            self.validate_create_xml(vals_list)
            _logger.error("validate_create_xml ok")

            # XML namespaces we may need
            ns = {
                "xhtml": "http://www.w3.org/1999/xhtml",
                "xh": "http://www.w3.org/1999/xhtml",  # alias used below
            }

            # --- 1) Preprocess XML for each payload ---
            for idx, vals in enumerate(vals_list):
                _logger.error("processing index=%s keys=%s", idx, list(vals.keys()))
                root = None

                try:
                    # from template?
                    if vals.get("builder_template_id"):
                        _logger.error("using builder_template_id=%s", vals["builder_template_id"])
                        template = self.env["orbeon.builder.template"].browse(vals["builder_template_id"])
                        xml_bytes = template.xml if isinstance(template.xml, (bytes, bytearray)) else (
                                template.xml or "").encode("utf-8")
                        root = etree.fromstring(xml_bytes)
                        _logger.error("template xml parsed: %s", root is not None)

                    # or from incoming xml field?
                    elif "xml" in vals and vals["xml"]:
                        _logger.error("using inline xml field")
                        xml_val = vals["xml"]
                        if isinstance(xml_val, (bytes, bytearray)):
                            xml_bytes = bytes(xml_val)
                        else:
                            xml_bytes = str(xml_val).encode("utf-8")
                        root = etree.fromstring(xml_bytes)
                        _logger.error("inline xml parsed: %s", root is not None)

                    else:
                        _logger.error("no xml source found in vals; skipping xml edits for this record")

                except Exception:
                    _logger.error("XML parsing failed at index=%s", idx, exc_info=True)
                    # choose: either raise (strict) or continue without XML edits
                    # raise ValidationError("Kon XML niet parsen; controleer het formulier/payload.")
                    root = None

                # Update XML nodes only if we have a root
                if root is not None:
                    try:
                        # //application-name (only if present in this template)
                        nodes = root.xpath("//application-name")
                        if nodes:
                            nodes[0].text = "odoo"
                            _logger.error("application-name set to 'odoo'")

                        # //form-name from vals['name']
                        if "name" in vals:
                            nodes = root.xpath("//form-name")
                            if nodes:
                                nodes[0].text = str(vals["name"])
                                _logger.error("form-name set to %r", vals["name"])

                        # Title handling (several possible locations)
                        title_val = vals.get("title")
                        if title_val:
                            # <metadata><title>
                            nodes = root.xpath("//metadata/title")
                            if nodes:
                                nodes[0].text = str(title_val)
                                _logger.error("metadata/title set to %r", title_val)

                            # bare //title (non-XHTML) if present
                            nodes = root.xpath("//title")
                            if nodes:
                                nodes[0].text = str(title_val)
                                _logger.error("//title set to %r", title_val)

                            # XHTML title <xhtml:title>
                            nodes = root.xpath("//xh:title", namespaces=ns)
                            if nodes:
                                nodes[0].text = str(title_val)
                                _logger.error("xhtml:title set to %r", title_val)

                        # write back
                        vals["xml"] = etree.tostring(root, encoding="unicode")
                        _logger.error("xml re-serialized for index=%s", idx)

                    except Exception:
                        _logger.error("XML mutation/serialization failed at index=%s", idx, exc_info=True)
                        # If desired, make this strict:
                        # raise ValidationError("Kon XML niet bijwerken.")
                        # Otherwise, leave original xml as-is.

            # --- 2) Create records ---
            records = super(OrbeonBuilder, self).create(vals_list)
            _logger.error("super().create returned %s records", len(records))

            # --- 3) Master linkage per created record ---
            # zip keeps the 1:1 mapping between incoming vals and created rec
            for rec, vals in zip(records, vals_list):
                try:
                    if "parent_id" not in vals:
                        master = self.env["orbeon.master"].create({"master_builder_id": rec.id})
                        rec.master_id = master.id
                        _logger.error("created master %s for builder %s", master.id, rec.id)
                    else:
                        master = self.env["orbeon.master"].search([("master_builder_id", "=", vals["parent_id"])],
                                                                  limit=1)
                        if master:
                            rec.master_id = master.id
                            _logger.error("linked builder %s to existing master %s", rec.id, master.id)
                        else:
                            _logger.error("no master found for parent_id=%s (builder %s)", vals["parent_id"], rec.id)
                except Exception:
                    _logger.error("post-create master linkage failed for builder %s", rec.id, exc_info=True)

            return records

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
                [list_view.id, "list"],
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

    def _current_builder(self):
        for record in self:
            query = """WITH RECURSIVE
                builder_children AS (
                SELECT
                    id, parent_id, name, state
                FROM
                    orbeon_builder
                WHERE id = {builder_id}
                    UNION ALL
                SELECT
                    ob.id, ob.parent_id, ob.name, ob.state
                FROM
                    builder_children AS bc
                    INNER JOIN orbeon_builder AS ob ON ob.parent_id = bc.id
                )
                SELECT id AS builder_id
                FROM builder_children
                WHERE state = '{state}' LIMIT 1
            """.format(builder_id=record.id, state=STATE_CURRENT)

            record.env.cr.execute(query)

            builder_id = record.env.cr.fetchone()
            if builder_id:
                record.current_builder_id = record.browse(builder_id[0])
            else:
                record.current_builder_id = False
                raise UserError(
                    "Er is geen huidige versie van het formulier ontwerp, neem contact op met de systeembeheerder!")

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

    def view_runner_forms(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("orbeon.orbeon_runner_form_action")
        action['domain'] = [
            ('builder_id', '=', self.id)
        ]
        action['context'] = {'default_builder_id': self.id}
        return action
