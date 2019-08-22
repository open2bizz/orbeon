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

FORMAT = "%(asctime)-15s %(log_lvl)-4s: %(message)s"
logging.basicConfig(format=FORMAT)
logger = logging.getLogger(__name__)
logger.setLevel(10)

def _log(type, msg):
    if type == "error":
        logger.error(msg, extra={"log_lvl": "Error"})
    elif type == "warning":
        logger.warning(msg, extra={"log_lvl": "Warning"})
    elif type == "debug":
        logger.debug(msg, extra={"log_lvl": "Debug"})
    elif type == "critical":
        logger.critical(msg, extra={"log_lvl": "Critical"})
    elif type == "exception":
        logger.exception(msg, extra={"log_lvl": "Exception"})
    elif type == "info":
        logger.info(msg, extra={"log_lvl": "Info"})
