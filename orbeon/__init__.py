# -*- coding: utf-8 -*-
##############################################################################
# Author: Open2Bizz (www.open2bizz.nl)
# Date: 2025-14-08
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
from . import models
from . import services
from . import controllers

def post_load():
    """
    Hook to start the persistence servers when Odoo starts.
    """
    from odoo import api, SUPERUSER_ID
    import odoo

    # We need a cursor to create an environment
    db_name = odoo.tools.config.get('db_name')
    if db_name:
        with odoo.registry(db_name).cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})
            # Call the autostart method from your model
            env['orbeon.server']._autostart_persistence_servers(env)