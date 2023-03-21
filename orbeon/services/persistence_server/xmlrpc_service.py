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
import xmlrpc.client
import logging
import base64

_logger = logging.getLogger(__name__)

class XMLRPCService(object):

    def __init__(self, db, uid, pwd, url):
        user = base64.b64decode(uid).decode('utf-8')
        passw = base64.b64decode(pwd).decode('utf-8')
        self.db = db
#        self.uid, self.pwd = uid,pwd 
        self.uid = user
        self.pwd = passw
        self.url = url
        self.connect()
        
    def connect(self):
        self.common = xmlrpc.client.ServerProxy("%s/xmlrpc/2/common" % self.url)
        self.api = xmlrpc.client.ServerProxy("%s/xmlrpc/2/object" % self.url)
        self.uid = self.common.authenticate(self.db, self.uid, self.pwd, {})

    def search(self, model, domain):
        """
        @param model: target model name
        @param domain: domain for search
        @type model: str
        @type domain: array of tuples in an array
        @return: array of integers
        """
        return self.api.execute_kw(self.db,self.uid,self.pwd, model, "search", domain)

    def search_read(self, model, domain, fields):
        """
        @param model: target model name
        @param domain: domain for search
        @param fields: fields to return
        @type model: str
        @type domain: array of tuples in an array
        @type fields: array of strings
        @return: array of dicts
        """
        return self.api.execute_kw(self.db,self.uid,self.pwd, model, "search_read", domain, {"fields":fields})

    def create(self, model, fields):
        """ 
        @param model: target model name 
        @param fields: fields and values for the to be created model
        @type model: str
        @type fields: single dictionary in an array
        @return: array of dicts
        """
        return self.api.execute_kw(self.db,self.uid,self.pwd, model, "create", fields)

    def write(self, model, id, fields):
    	"""
    	@param model: target model name
    	@param id: record id
    	@param fields: fields and values to write to record
    	@type model: str
    	@type id: int
    	@type fields: dictionary in an array
    	@return: ??
    	"""
    	return self.api.execute_kw(self.db,self.uid,self.pwd, model, "write", [[id], fields])

    def unlink(self, model, id):
        """
        @param model: target model name
        @param id: target record id
        @type model: str
        @type id: int
        @return: ??
        """
        return self.api.execute_kw(self.db, self.uid, self.pwd, model, "unlink", [[id]])

    def builder_search_read_data(self, domain, fields):
        """
        @param domain: domain for search
        @param fields: fields to return
        @type domain: array of tuples in an array
        @type fields: array of strings
        @return: array of dicts
        """
        return self.api.execute_kw(self.db, self.uid, self.pwd, "orbeon.builder", "orbeon_search_read_data", domain, {"fields":fields})

    def runner_search_read_builder(self, domain, fields):
        """
        @param domain: domain for search
        @param fields: fields to return
        @type domain: array of tuples in an array
        @type fields: array of strings
        @return: array of dicts
        """
        _logger.error(self.uid)
        return self.api.execute_kw(self.db, self.uid, self.pwd, "orbeon.runner", "orbeon_search_read_builder", domain, {"fields":fields})
        
    def runner_search_read_data(self, domain, fields):
        """
        @param domain: domain for search
        @param fields: fields to return
        @type domain: array of tuples in an array
        @type fields: array of strings
        @return: array of dicts
        """

        return self.api.execute_kw(self.db, self.uid, self.pwd, "orbeon.runner", "orbeon_search_read_data", domain, {"fields":fields})
