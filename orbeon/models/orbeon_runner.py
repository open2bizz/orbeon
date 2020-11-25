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
from orbeon_xml_api.builder import Builder as BuilderAPI
from orbeon_xml_api.runner import Runner as RunnerAPI
from orbeon_xml_api.runner_copy_builder_merge import RunnerCopyBuilderMerge as RunnerCopyBuilderMergeAPI

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


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
    _inherit = ['mail.thread']
    _description = 'Orbeon Runner'

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
        ondelete='restrict',
        help="Database ID of the record in res_model to which this applies")

    any_new_current_builder = fields.Boolean(
        "Any New Current Builder",
        compute="_any_new_current_builder",
        readonly=True)

    @api.one
    def _get_builder_name(self, id=None):
        if self.res_model != False and self.res_id != 0:
            self.builder_name = "%s v.%s (%s)" % (self.builder_id.name, self.builder_id.version, self.env[self.res_model].browse(self.res_id).display_name)
        else:
            self.builder_name = "%s v.%s" % (self.builder_id.name, self.builder_id.version)
            
    @api.one
    def _get_builder_version(self, id=None):
        self.builder_version = self.builder_id.version

    @api.one
    def _get_builder_title(self, id=None):
        self.builder_title = self.builder_id.title

    @api.depends('builder_id')
    def _get_res_model(self):
        self.res_model = self.builder_id.res_model_id.model

    @api.multi
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
                path_mode = get_mode.get(rec.state, 'view')
                url = "%s/%s/%i" % (base_url, path_mode, rec.id)

            rec.url = url

    @api.multi
    def _any_new_current_builder(self):
        self.ensure_one()

        if not self.builder_id.current_builder_id.id:
            self.any_new_current_builder = False
        else:
            self.any_new_current_builder = (self.builder_id.id != self.builder_id.current_builder_id.id)

    @api.multi
    def action_open_orbeon_runner(self):
        self.ensure_one()
        for rec in self:
            if (self.builder_id.id != self.builder_id.current_builder_id.id):
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

    @api.multi
    def action_send_versionupdate(self, old_builder_id, new_builder_id):       
        for rec in self:
            body = "Er is een nieuwe versie beschikbaar van dit formulier!\nDe versie van dit formulier is nu geupdate van %s naar %s." % (old_builder_id,new_builder_id)
            rec.message_post(body=body)

    @api.multi
    def write(self, vals):
        if 'is_merged' not in vals:
            if vals.get('builder_id', False) and vals['builder_id'] != self.builder_id:
                raise ValidationError("Changing the builder is not allowed.")

        res = super(OrbeonRunner, self).write(vals)
        return res

    @api.multi
    def copy(self, default=None):
        runner = super(OrbeonRunner, self).copy(default)
        ctx = self._context.copy()
        runner.with_context(ctx).merge_current_builder()
        return runner

    @api.multi
    def can_merge(self):
        """Can this Runner (xml) be merged with a new current Builder? """
        self.ensure_one()

        if not self.xml:
            return False
        else:
            return True

    @api.multi
    @api.returns('self')
    def merge_current_builder(self):
        """ Merge (and replace) this Runner XML with XML from the current/published Builder """
        if not self.can_merge():
            return False

        try:
            # Do the real merge
            return self.merge_builder(self.builder_id.current_builder_id)
        except Exception as e:
            _logger.error("Orbeon Runner merge Exception: %s" % e)
            raise UserError("Orbeon Runner merge Exception: %s" % e)

    @api.one
    @api.returns('self')
    def merge_builder(self, builder_obj):
        """ Merge (and replace) this Runner XML with XML from builder_obj """
        context = self._context

        if 'lang' in context:
            lang = context['lang']
        elif 'lang' not in context and 'uid' in context:
            lang = self.env['res.users'].browse(context['uid']).lang
        elif 'lang' not in context and 'uid' not in context:
            lang = self.env['res.users'].browse(self.write_uid.id).lang
        else:
            raise UserError("The form can't be loaded. No (user) language was set.")

        res_lang = self.env['res.lang'].search([('code', '=', lang)], limit=1)
        # This Runner
        builder_xml = u'%s' % self.builder_id.xml
        builder_xml = bytes(bytearray(builder_xml, encoding='utf-8'))
        builder_api = BuilderAPI(builder_xml, res_lang.iso_code)

        runner_xml = u'%s' % self.xml
        runner_xml = bytes(bytearray(runner_xml, encoding='utf-8'))

        runner_api = RunnerAPI(runner_xml, builder_api)

        # Builder to be merged with
        merge_builder_xml = u'%s' % builder_obj.xml
        merge_builder_xml = bytes(bytearray(merge_builder_xml, encoding='utf-8'))
        merge_builder_api = BuilderAPI(merge_builder_xml, res_lang.iso_code)
        try:
            # TODO Store the no_copy_prefix per orbeon.builder record (as field)?
            merger_api = RunnerCopyBuilderMergeAPI(runner_api, merge_builder_api, no_copy_prefix='NC.')
            merged_runner = merger_api.merge()

            self.write({
                'xml': merged_runner.xml,
                'builder_id': builder_obj.id,
                'is_merged': True
            })

            return self
        except Exception as e:
            _logger.error("[orbeon] Merge failed with error: %s" % e)
            raise UserError("Merge failed with error: %s" % e)

    # TODO
    # @api.multi
    # def duplicate_runner_form(self):
    #     alter = {}
    #     alter["state"] = STATE_NEW
    #     alter["is_merged"] = False
    #     # XXX maybe useless if merge_xml_current_builder() returns None?
    #     alter["xml"] = self.merge_xml_current_builder()
    #     super(OrbeonRunner, self).copy(alter)

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
                xml = '<?xml version="1.0" encoding="utf-8"?>%s' % \
                             runner.builder_id.get_xml_form_node()[0]
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
            runner.message_post(body=message, content_subtype='plaintext')

        return parser.xml

    def write_rec_model_name(self):
        model = self.env['ir.model'].browse(self.builder_id.res_model_id.id)
        for obj in model:
            rec = self.env[obj.model].browse(self.res_id)
            self.write({'model_record_name':rec.name})
