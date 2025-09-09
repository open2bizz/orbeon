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
import logging
_logger = logging.getLogger(__name__)
_logger.error("import logging done")

import copy
_logger.error("import copy done")

import re
_logger.error("import re done")

import sys
_logger.error("import sys done")

import datetime
_logger.error("import datetime done")


_logger.error("_logger created")

ERP_FIELD_PREFIX = 'ERP'
_logger.error(f"ERP_FIELD_PREFIX={ERP_FIELD_PREFIX}")

UNKNOWN_ERP_FIELD = 'UNKNOWN ERP-FIELD'
_logger.error(f"UNKNOWN_ERP_FIELD={UNKNOWN_ERP_FIELD}")

relational_field_error = False
_logger.error(f"relational_field_error={relational_field_error}")

class XMLParserERPFieldsException(Exception):
    _logger.error("Defining class XMLParserERPFieldsException")

    def __init__(self, msg):
        _logger.error("XMLParserERPFieldsException.__init__ entered")
        self.message = "[ERROR: ERP-Field] %s" % msg
        _logger.error(f"self.message={self.message}")


class XmlParserBase(object):
    _logger.error("Defining class XmlParserBase")

    def __init__(self, runner, xml_root):
        _logger.error("XmlParserBase.__init__ entered")
        self.runner = runner
        _logger.error(f"runner={runner}")

        self.xml_root = xml_root
        _logger.error(f"xml_root={xml_root}")

        self.erp_fields = None
        _logger.error("erp_fields=None")

        self.res_object = None
        _logger.error("res_object=None")

        self.res_model = self.runner.builder_id.res_model_id.model
        _logger.error(f"res_model={self.res_model}")

        self.errors = []
        _logger.error("errors initialized []")


class XmlParserERPFields(XmlParserBase):
    _logger.error("Defining class XmlParserERPFields")

    def __init__(self, runner, xml_root):
        _logger.error("XmlParserERPFields.__init__ entered")
        super(XmlParserERPFields, self).__init__(runner, xml_root)
        _logger.error("super().__init__ called")

        self.load_erp_fields()
        _logger.error("self.load_erp_fields done")

        if not self.has_erp_fields():
            _logger.error("No ERP fields found")
            _logger.error("No ERP fields found for model %s in provided XML.", self.res_model)
            return
        _logger.error("ERP fields exist")

        self.load_res_object()
        _logger.error("self.load_res_object done")

    def has_erp_fields(self):
        _logger.error("XmlParserERPFields.has_erp_fields called")
        return self.erp_fields is not None

    def load_erp_fields(self):
        _logger.error("XmlParserERPFields.load_erp_fields called")

        query = "//*[starts-with(local-name(), '%s.')]" % ERP_FIELD_PREFIX
        _logger.error(f"XPath query={query}")

        res = self.xml_root.xpath(query)
        _logger.error(f"XPath result length={len(res)}")

        if len(res) == 0:
            _logger.error("No ERP fields found in XML")
            return

        self.erp_fields = {}
        _logger.error("erp_fields initialized {}")

        for element in res:
            self.erp_fields[element.tag] = ERPField(element.tag, element)
            _logger.error(f"ERPField created tag={element.tag}")

        _logger.error('Read ERP-fields: %s\n For model: %s', list(self.erp_fields.keys()), self.res_model)

    def load_res_object(self):
        _logger.error("XmlParserERPFields.load_res_object called")
        if not self.has_erp_fields():
            _logger.error("No ERP fields present, abort load_res_object")
            return
        try:
            self.res_object = self.runner.env[self.runner.builder_id.res_model_id.model].browse(self.runner.id)
            _logger.error(f"res_object loaded id={self.runner.id}")
        except Exception:
            _logger.error("Failed to load res_object for model %s with id %s.", self.runner.builder_id.res_model_id.model, self.runner.id, exc_info=True)
            raise

    def parse(self):
        _logger.error("XmlParserERPFields.parse called")
        global relational_field_error
        if not self.has_erp_fields():
            _logger.error("No ERP fields, nothing to parse")
            return
        for tagname, erp_field_obj in self.erp_fields.items():
            _logger.error(f"Parsing tag={tagname}")

            target_object = self.res_object
            _logger.error("target_object set to res_object")

            model_fields = copy.copy(erp_field_obj.model_fields)
            _logger.error(f"model_fields copied {model_fields}")

            all_fields = []
            _logger.error("all_fields initialized []")

            traversed_fields = []
            _logger.error("traversed_fields initialized []")

            while len(model_fields) > 1:
                _logger.error(f"while loop model_fields={model_fields}")
                field = model_fields.pop(0)
                _logger.error(f"field popped {field}")

                all_fields.append(field)
                _logger.error(f"all_fields now {all_fields}")
                try:
                    target_object = target_object[field]
                    _logger.error(f"Traversed into field {field}")
                    traversed_fields.append(field)
                    _logger.error(f"traversed_fields {traversed_fields}")
                except KeyError as relational_field_error:
                    msg = "NOT IN MODEL %s" % self.res_model
                    _logger.error(msg)
                    error = self._exception_erpfield(erp_field_obj.tagname, all_fields, msg)
                    _logger.error('[orbeon] %s', error.message, exc_info=True)
                except Exception as relational_field_error:
                    msg = "ERROR with model %s" % self.res_model
                    _logger.error(msg)
                    error = self._exception_erpfield(erp_field_obj.tagname, all_fields, msg)
                    _logger.error('[orbeon] %s', error.message, exc_info=True)

            all_fields.append(model_fields[0])
            _logger.error(f"Final field chain {all_fields}")

            if all_fields:
                try:
                    field = model_fields[0]
                    _logger.error(f"Final field={field}")
                    field_val = target_object[field]
                    _logger.error(f"field_val={field_val}")
                    if isinstance(field_val, datetime.date):
                        field_val = field_val.isoformat()
                        _logger.error(f"field_val isoformatted={field_val}")
                except KeyError:
                    msg = "NOT IN MODEL %s" % self.res_model
                    error = self._exception_erpfield(erp_field_obj.tagname, all_fields, msg)
                    _logger.error(msg)

                    if self.runner.builder_id.debug_mode:
                        field_val = error.message
                        _logger.error(f"field_val={field_val}")
                    else:
                        field_val = UNKNOWN_ERP_FIELD
                        _logger.error("field_val set to UNKNOWN_ERP_FIELD")

                    _logger.error('[orbeon] %s', error.message)
                    self.errors.append(error)
                    _logger.error("error appended")
                except Exception as e:
                    error = self._exception_erpfield(erp_field_obj.tagname, all_fields, e)
                    _logger.error("Exception while resolving field")

                    if self.runner.builder_id.debug_mode:
                        field_val = error.message
                        _logger.error(f"field_val={field_val}")
                    else:
                        field_val = UNKNOWN_ERP_FIELD
                        _logger.error("field_val set to UNKNOWN_ERP_FIELD")

                    _logger.error('[orbeon] %s', error.message, exc_info=True)
                    self.errors.append(error)
                    _logger.error("error appended")
            else:
                if self.runner.builder_id.debug_mode:
                    field_val = error.message
                    _logger.error(f"field_val={field_val}")
                else:
                    field_val = UNKNOWN_ERP_FIELD
                    _logger.error("field_val set to UNKNOWN_ERP_FIELD")
                _logger.error('[orbeon] No value resolved for %s (chain: %s)', erp_field_obj.tagname, ".".join(erp_field_obj.model_fields))

            erp_field_obj.set_element_text(field_val)
            _logger.error(f"Element text set for {erp_field_obj.tagname}")

    def _exception_erpfield(self, tagname, fields_chain, msg):
        _logger.error("XmlParserERPFields._exception_erpfield called")
        msg_exception = "%s (ERP.%s %s)" % (tagname, (".".join(fields_chain)), msg)
        _logger.error(f"msg_exception={msg_exception}")
        return XMLParserERPFieldsException(msg_exception)


class ERPField(object):
    _logger.error("Defining class ERPField")

    def __init__(self, tagname, element):
        _logger.error("ERPField.__init__ called")
        self.tagname = tagname
        _logger.error(f"tagname={tagname}")
        self.element = element
        _logger.error(f"element={element}")

        re_pattern = r'^%s\.' % ERP_FIELD_PREFIX
        _logger.error(f"re_pattern={re_pattern}")

        erp_field_token = re.sub(re_pattern, '', self.tagname)
        _logger.error(f"erp_field_token={erp_field_token}")

        self.model_fields = erp_field_token.split('.')
        _logger.error(f"model_fields={self.model_fields}")

    def set_element_text(self, value):
        _logger.error("ERPField.set_element_text called with %r", value)
        try:
            if value in (None, False):
                text = ""
            elif isinstance(value, (datetime.date, datetime.datetime)):
                text = value.isoformat()
            else:
                text = str(value)
            self.element.text = text
            _logger.error("element.text set to %r", text)
        except Exception:
            _logger.error("Failed setting element text for %s with value %r.", self.tagname, value, exc_info=True)