# -*- coding: utf-8 -*-
"""
/***************************************************************************
 StraboSpot
                                 A QGIS plugin
 Download and Upload Strabo data to and from QGIS. 
                             -------------------
        begin                : 2017-06-15
        copyright            : (C) 2017 by Emily Bunse - University of Kansas
        email                : egbunse@gmail.com
        git sha              : $Format:%H$
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
 This script initializes the plugin, making it known to QGIS.
"""


# noinspection PyPep8Naming
def classFactory(iface):  # pylint: disable=invalid-name
    """Load StraboSpot class from file StraboSpot.

    :param iface: A QGIS interface instance.
    :type iface: QgsInterface
    """
    #
    from .strabo_spot import StraboSpot
    return StraboSpot(iface)
