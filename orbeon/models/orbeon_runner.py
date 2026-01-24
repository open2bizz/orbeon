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

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from lxml import etree
import xmltodict
import pprint
import json
import random
import string
from datetime import datetime, timedelta
from ..services.runner_xml_parser import runner_xml_parser

import logging
_logger = logging.getLogger(__name__)

STATE_NEW = 'new'
STATE_PROGRESS = 'progress'
STATE_COMPLETE = 'complete'
STATE_CANCELED = 'canceled'
STATE_TEMPLATE = 'template'


class OrbeonRunner(models.Model):
    _name = 'orbeon.runner'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Formulier'

    _rec_name = "builder_name"

    active = fields.Boolean(default=True)

    builder_id = fields.Many2one(
        "orbeon.builder",
        string="Form builder",
        ondelete='restrict',
        store=True)

    builder_name = fields.Char(
        "Builder Name",
        compute="_get_builder_name",
        readonly=True)

    builder_version = fields.Integer(
        "Builder Version",
        compute="_get_builder_version",
        readonly=True)

    builder_title = fields.Char(
        "Builder Title",
        compute="_get_builder_title",
        readonly=True)

    model_record_name = fields.Char(
        "Model Record Name",
        readonly=True
    )

    color = fields.Integer('Color Index')

    state = fields.Selection(
        [
            (STATE_NEW, "New"),
            (STATE_PROGRESS, "In Progress"),
            (STATE_COMPLETE, "Complete"),
            (STATE_CANCELED, "Canceled"),
            (STATE_TEMPLATE, "Template"),
        ],
        string="State",
        default=STATE_NEW)

    """Lets us know if this filed is merged with latest builder fields."""
    is_merged = fields.Boolean(
        'Is Merged',
        default=False)

    xml = fields.Text(
        'XML',
        default=False)

    url = fields.Text(
        'URL',
        compute="_get_url",
        readonly=True)

    # TODO:
    # Change to Many2one (res_model_id) and add migation (res_model => res_model_id)
    res_model = fields.Char(
        "Resource Model",
        compute="_get_res_model",
        readonly=True,
        store=True)

    res_id = fields.Integer(
        "Record ID",
        help="Database ID of the record in res_model to which this applies")

    any_new_current_builder = fields.Boolean(
        "Any New Current Builder",
        compute="_any_new_current_builder",
        readonly=True)

    #This is a field that is set when form is openend, passwords are nog longer accessible via HTML Headers (are encrypted) and we need to identify certain actions with this user.
    current_orbeon_user = fields.Many2one('res.users')

    def _get_builder_name(self, id=None):
        for record in self:
            try:
                #record.builder_name = "_Unknown"
                if record.res_model != False and record.res_id != 0:
                    record.builder_name = "%s v.%s (%s)" % (record.builder_id.name, record.builder_id.version, record.env[record.res_model].browse(record.res_id).display_name)
                else:
                    record.builder_name = "%s v.%s" % (record.builder_id.name or "_Unknown", record.builder_id.version or "1")
            except:
                record.builder_name = "_Unknown"

    def _get_builder_version(self, id=None):
        for record in self:
            record.builder_version = record.builder_id.version

    def _get_builder_title(self, id=None):
        for record in self:
            record.builder_title = record.builder_id.title

    @api.depends('builder_id')
    def _get_res_model(self):
        self.res_model = self.builder_id.res_model_id.model

    def _compute_can_edit(self):
        for record in self:
            if record.state == STATE_PROGRESS:
                return True
            else:
                return False

    @api.onchange('builder_id')
    def _get_url(self):
        for rec in self:
            if isinstance(rec.id, models.NewId) and not rec.builder_id.id:
                return rec.url

            base_path = 'fr/b!%s!%s/runner' % (rec.builder_id.id, rec.id)
            base_url = "/orbeon/%s" % (base_path)

            if isinstance(rec.id, models.NewId):
                url = "%s/new" % base_url
            else:
                get_mode = {STATE_NEW: 'edit', STATE_PROGRESS: 'edit'}
                path_mode = get_mode.get(rec.state, 'edit')
                url = "%s/%s/%i" % (base_url, path_mode, rec.id)

            rec.url = url

    def _any_new_current_builder(self):
        for record in self:
            record.any_new_current_builder = False
            if not record.builder_id.current_builder_id.id:
                record.any_new_current_builder = False
            else:
                record.any_new_current_builder = (record.builder_id.id != record.builder_id.current_builder_id.id)

    def action_open_orbeon_runner_view(self):
        self.ensure_one()
        return self.open_orbeon_runner(edit_mode=False)

    def action_open_orbeon_runner_edit(self):
        self.ensure_one()
        return self.open_orbeon_runner(edit_mode=True)

    def open_orbeon_runner(self, edit_mode=True):
        self.ensure_one()
        if edit_mode:
            self.current_orbeon_user = self.env.uid
        #2FA Orbeon
        user = self.env['res.users'].browse(self.env.uid)
        if not user.api_key and user.totp_enabled:
            raise UserError(
                "Two-Factor authentication is configured, but the API key is missing in the user profile. \n"
                "For more information, please refer to the documentation: \n"
                "https://www.odoo.com/documentation/16.0/developer/reference/external_api.html?highlight=api%20key#api-keys",
            )
        if edit_mode:
            if self.xml == False and (self.builder_id.id != self.builder_id.current_builder_id.id):
                # zet de nieuwe builder versie
                old_builder_id = self.builder_id.display_name
                new_builder_id = self.builder_id.current_builder_id.display_name
                new_builder_id_id = self.builder_id.current_builder_id.id
                self.write({'builder_id': new_builder_id_id})
                self.action_send_versionupdate(old_builder_id, new_builder_id)
        return {
            'name': 'Orbeon',
            'type': 'ir.actions.act_url',
            'target': 'new',
            'url': self.url
        }
  
    def write(self, vals):
        #if 'is_merged' not in vals:
        #    if vals.get('builder_id', False) and vals['builder_id'] != self.builder_id:
        #        raise ValidationError("Changing the builder is not allowed.")

        res = super(OrbeonRunner, self).write(vals)
        return res

    def action_send_versionupdate(self, old_builder_id, new_builder_id):       
        for rec in self:
            body = "Er is een nieuwe versie beschikbaar van dit formulier!\nDe versie van dit formulier is nu geupdate van %s naar %s." % (old_builder_id,new_builder_id)
            rec.message_post(body=body)
   
    def copy(self, default=None):
        for record in self:
            runner = super(OrbeonRunner, record).copy(default)
            ctx = record._context.copy()
            runner.with_context(ctx).merge_current_builder()
        return runner

    def can_merge(self):
        """Can this Runner (xml) be merged with a new current Builder? """
        self.ensure_one()

        if not self.xml:
            return False
        else:
            return True

    # @api.returns('self')
    # def merge_current_builder(self):
    #     """ Merge (and replace) this Runner XML with XML from the current/published Builder """
    #     # Todo version 18. Refactor! Function merge_builder() was removed because of XML api dependance
    #     return True
    #     # if not self.can_merge():
    #     #     return False
    #     # return self.merge_builder(self.builder_id.current_builder_id)

    @api.model
    def orbeon_search_read_builder(self, domain=None, fields=None):
        runner = self.search(domain or [], limit=1)
        builder = runner.builder_id

        res = {'id': builder['id']}

        if 'xml' in fields:
            res['xml'] = builder.xml

        return res

    @api.model
    def orbeon_search_read_data(self, domain=None, fields=None):
        runner = self.search(domain or [], limit=1)

        res = {'id': runner['id']}

        if 'xml' in fields:
            if runner.xml is None or runner.xml is False:
                # TODO
                # preprend the <xml> tag from elsewhere? Via builder-API to get right version?
                # code: runner.builder_id.get_xml_form_node(with_xml_tag)
                xml = '<?xml version="1.0" encoding="utf-8"?>%s' % runner.builder_id.get_xml_form_node()
            else:
                xml = runner.xml

        xml = self.parse_runner_xml(xml, runner)
        res['xml'] = bytes(bytearray(xml, encoding='utf-8'))

        return res

    def parse_runner_xml(self, xml, runner):
        parser = runner_xml_parser.RunnerXmlParser(xml, runner)
        parser.parse()

        if runner.builder_id.debug_mode:
            message = "\r\n".join([e.message for e in parser.errors])
            runner.message_post(body=str(message))

        return parser.xml

    def write_rec_model_name(self):
        model = self.env['ir.model'].browse(self.builder_id.res_model_id.id)

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
                _logger.error("Failed to pretty print XML: %s", str(e))
                raise UserError(_("Invalid XML format: %s") % str(e))

    def action_generate_test_xml(self):
        """ Generates random test data based on the builder definition """
        self.ensure_one()
        if not self.builder_id.xml:
            raise UserError(_("The linked builder has no XML definition."))

        parser = etree.XMLParser(ns_clean=True, recover=True, encoding='utf-8')
        root = etree.fromstring(self.builder_id.xml.encode('utf-8'), parser)
        namespaces = {
            'xf': 'http://www.w3.org/2002/xforms',
            'fr': 'http://orbeon.org/oxf/xml/form-builder',
            'xh': 'http://www.w3.org/1999/xhtml'
        }

        # 1. Map Binds to types
        binds = root.xpath("//xf:bind[@id]", namespaces=namespaces)
        type_mapping = {}
        for bind in binds:
            ref = bind.get('ref')
            field_name = ref.split('/')[-1] if ref else None
            if field_name:
                type_mapping[field_name] = bind.get('type') or 'xf:string'

        # 2. Extract selection options from fr-form-resources
        selection_options = {}
        resource_nodes = root.xpath("//xf:instance[@id='fr-form-resources']//resource/*[item]", namespaces=namespaces)
        for res in resource_nodes:
            field_name = etree.QName(res).localname
            values = res.xpath("./item/value/text()")
            if values:
                selection_options[field_name] = {
                    'values': values,
                    'multiple': False  # Default to single select
                }

        # 3. Refine 'multiple' selection based on UI components
        # Find xf:select (multiple) vs xf:select1 / fr:dropdown-select1 (single)
        multi_selects = root.xpath("//xf:select", namespaces=namespaces)
        for ctrl in multi_selects:
            # Try to find the field name from bind or ref
            ref = ctrl.get('bind') or ctrl.get('ref')
            if ref:
                # remove -bind suffix if present and get last part
                fname = ref.replace('-bind', '').split('/')[-1]
                if fname in selection_options:
                    selection_options[fname]['multiple'] = True

        # 4. Get the form structure template
        form_template_node = root.xpath("//xf:instance[@id='fr-form-instance']/form", namespaces=namespaces)[0]
        
        def generate_random_value(field_name, data_type):
            # Check if it's a selection field (Dropdown, Radio, Checkboxes)
            if field_name in selection_options:
                opts = selection_options[field_name]
                if opts['multiple']:
                    # Pick 1 to N random values, space-separated for Orbeon checkboxes
                    count = random.randint(1, len(opts['values']))
                    return ' '.join(random.sample(opts['values'], count))
                else:
                    return random.choice(opts['values'])

            # Fallback to type-based generation
            if data_type == 'xf:date':
                return (datetime.now() - timedelta(days=random.randint(0, 3650))).strftime('%Y-%m-%d')
            elif data_type == 'xf:dateTime':
                return (datetime.now() - timedelta(days=random.randint(0, 3650))).strftime('%Y-%m-%dT%H:%M:%S')
            elif data_type in ['xf:integer', 'xf:decimal', 'xf:number']:
                return str(random.randint(1, 1000))
            elif data_type == 'xf:boolean':
                return random.choice(['true', 'false'])
            elif data_type == 'xf:anyURI':
                return "http://example.com/test.png"
            else:
                return ''.join(random.choices(string.ascii_letters, k=10))

        def fill_node(node):
            for child in node:
                tag = etree.QName(child).localname
                # Rule 1: Skip ERP fields
                if tag.startswith('ERP'):
                    child.text = ''
                    continue
                
                if len(child) > 0:
                    fill_node(child)
                else:
                    data_type = type_mapping.get(tag, 'xf:string')
                    child.text = generate_random_value(tag, data_type)

        # Generate result
        test_form = etree.fromstring(etree.tostring(form_template_node))
        fill_node(test_form)

        xml_result = etree.tostring(test_form, encoding='unicode', pretty_print=True)
        self.xml = f'<?xml version="1.0" encoding="UTF-8"?>\n{xml_result}'

        return True
