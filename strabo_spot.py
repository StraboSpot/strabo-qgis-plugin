# -*- coding: utf-8 -*-
"""
/***************************************************************************
 StraboSpot
                                 A QGIS plugin
 Download and Upload Strabo data to and from QGIS. 
                              -------------------
        begin                : 2017-06-15
        git sha              : $Format:%H$
        copyright            : (C) 2017 by Emily Bunse - University of Kansas
        email                : egbunse@gmail.com
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/

 **********Remember to add a list of the functions and briefly describe what they do.
 List them by category under download and upload... *********************************

 Widget List (from StraboSpotDialog)
 0: login
 1: DownloadOrUpload
 2: StraboChoose
 3: downloadOptions
 4: postGIS_info
 5: downloadProgress
 6: uploadDatasets

 Function List (in class StraboSpot)

"""
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QAction, QFileDialog, QMessageBox, QApplication
from PyQt5.QtCore import QCoreApplication, QSettings, QTranslator, qVersion
from PyQt5.QtSql import QSqlDatabase
from qgis.core import QgsMessageLog, QgsVectorFileWriter, QgsVectorLayer, QgsProject, QgsDataSourceUri, QgsCoordinateReferenceSystem, Qgis
from qgis.gui import QgsMessageBar
import qgis.utils

# from pyspatialite import dbapi2 as db
from qgis.utils import spatialite_connect

# Initialize Qt resources from file resources.py
from . import resources
# Import the code for the dialog
from .strabo_spot_dialog import StraboSpotDialog
import os.path
import requests
import json
import errno
import datetime
import shutil
import piexif
import math
import psycopg2
import numpy
import time
from requests.auth import HTTPBasicAuth
from PIL import Image
from PIL import ImageFile
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from osgeo import gdal
from tempfile import mkstemp, gettempdir


class StraboSpot:
    """QGIS Plugin Implementation."""
    # These are global variables
    global username, password, projectid, projectids, datasetids, projectname,\
        requestImages, fileExte, chosendatasets, selDB,\
        upload_layer_list, sel_upload_method, temp_folder
    username = None
    password = None
    projectid = None
    projectids = []
    datasetids = []
    projectname = None
    requestImages = False
    fileExte = None
    chosendatasets = []
    selDB = None
    # Upload vars
    upload_layer_list = []
    sel_upload_method = None
    temp_folder = None

    def __init__(self, iface):
        """Constructor.

        :param iface: An interface instance that will be passed to this class
            which provides the hook by which you can manipulate the QGIS
            application at run time.
        :type iface: QgsInterface
        """
        # Save reference to the QGIS interface
        self.iface = qgis.utils.iface
        # initialize plugin directory
        self.plugin_dir = os.path.dirname(__file__)
        # initialize locale
        locale = QSettings().value('locale/userLocale')[0:2]
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            'StraboSpot_{}.qm'.format(locale))

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)

            if qVersion() > '4.3.3':
                QCoreApplication.installTranslator(self.translator)

        # Create the dialog (after translation) and keep reference
        self.dlg = StraboSpotDialog()

        # Declare instance attributes
        self.actions = []
        self.menu = self.tr(u'&StraboSpot')
        self.toolbar = self.iface.addToolBar(u'StraboSpot')
        self.toolbar.setObjectName(u'StraboSpot')
        # Handle all the back buttons- they are all handled by same function
        self.dlg.backtologinpushButton.clicked.connect(self.backdialog)
        self.dlg.backto2pushButton.clicked.connect(self.backdialog)
        self.dlg.backtodatasetspushButton.clicked.connect(self.backdialog)
        self.dlg.back2pushButton.clicked.connect(self.backdialog)
        # Handle all the download choices made by the user
        self.dlg.loginpushButton.clicked.connect(self.handleLoginButton)
        # Adding extra args to qt slot: https://eli.thegreenplace.net/2011/04/25/passing-extra-arguments-to-pyqt-slot
        self.dlg.getProjectspushButton.clicked.connect(lambda: self.getprojects("projectlistWidget"))
        self.dlg.projectlistWidget.itemClicked.connect(lambda: self.getprojectid("projectlistWidget"))
        self.dlg.datasetlistWidget.itemClicked.connect(self.getdatasetid)
        self.dlg.toOptionspushButton.clicked.connect(self.downloadOptionsGUI)
        self.dlg.downloadradioButton.clicked.connect(self.deploydownloadGUI)
        self.dlg.browsepushButton.clicked.connect(self.filebrowse)
        self.dlg.importpushButton.clicked.connect(self.importSpots)
        self.dlg.jpegradioButton.clicked.connect(self.setJpeg)
        self.dlg.tiffradioButton.clicked.connect(self.setTiff)
        self.dlg.postGISButton.clicked.connect(self.setPostGIS)
        self.dlg.spatiaLiteButton.clicked.connect(self.setSpatiaLite)
        # Handle some of the upload choices made by the user
        self.dlg.uploadradioButton.clicked.connect(self.deployuploadGUI)
        self.dlg.qgislayers.itemClicked.connect(self.chosen_layers)
        self.dlg.overwrite_upload.clicked.connect(self.set_overwrite)
        self.dlg.create_new_upload.clicked.connect(self.set_create)
        self.dlg.choose_datasets_button.clicked.connect(self.setup_upload_confirm)
        self.dlg.upload_next_button.clicked.connect(self.upload_dataset)
        self.dlg.create_prj_widget.itemClicked.connect(lambda: self.getprojectid("create_prj_widget"))

        # Set up the Message Bar in QGIS for showing the user errors
        self.bar = QgsMessageBar()

        # Set the website label options (user can go to StraboSpot site from plug-in)
        self.dlg.websitelabel.setText('<a href="https://strabospot.org">Visit StraboSpot</a>')
        self.dlg.websitelabel.setOpenExternalLinks(True)

        # Create a QgsProject instance to manage layers
        self._qgs_project = QgsProject()

    # noinspection PyMethodMayBeStatic
    def tr(self, message):
        """Get the translation for a string using Qt translation API.

        We implement this ourselves since we do not inherit QObject.

        :param message: String for translation.
        :type message: str, QString

        :returns: Translated version of message.
        :rtype: QString
        """
        # noinspection PyTypeChecker,PyArgumentList,PyCallByClass
        return QCoreApplication.translate('StraboSpot', message)

    def add_action(
            self,
            icon_path,
            text,
            callback,
            enabled_flag=True,
            add_to_menu=True,
            add_to_toolbar=True,
            status_tip=None,
            whats_this=None,
            parent=None):
        """Add a toolbar icon to the toolbar.

        :param icon_path: Path to the icon for this action. Can be a resource
            path (e.g. ':/plugins/foo/bar.png') or a normal file system path.
        :type icon_path: str

        :param text: Text that should be shown in menu items for this action.
        :type text: str

        :param callback: Function to be called when the action is triggered.
        :type callback: function

        :param enabled_flag: A flag indicating if the action should be enabled
            by default. Defaults to True.
        :type enabled_flag: bool

        :param add_to_menu: Flag indicating whether the action should also
            be added to the menu. Defaults to True.
        :type add_to_menu: bool

        :param add_to_toolbar: Flag indicating whether the action should also
            be added to the toolbar. Defaults to True.
        :type add_to_toolbar: bool

        :param status_tip: Optional text to show in a popup when mouse pointer
            hovers over the action.
        :type status_tip: str

        :param parent: Parent widget for the new action. Defaults None.
        :type parent: QWidget

        :param whats_this: Optional text to show in the status bar when the
            mouse pointer hovers over the action.

        :returns: The action that was created. Note that the action is also
            added to self.actions list.
        :rtype: QAction
        """
        icon_path = ":/plugins/StraboSpot/strabologo.png"
        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            self.toolbar.addAction(action)

        if add_to_menu:
            self.iface.addPluginToMenu(
                self.menu,
                action)

        self.actions.append(action)

        return action

    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""

        icon_path = ':/plugins/StraboSpot/icon.png'
        self.add_action(
            icon_path,
            text=self.tr(u'Download/Upload Strabo Data'),
            callback=self.run,
            parent=self.iface.mainWindow())

    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""
        for action in self.actions:
            self.iface.removePluginMenu(
                self.tr(u'&StraboSpot'),
                action)
            self.iface.removeToolBarIcon(action)
        # remove the toolbar
        del self.toolbar

    def backdialog(self):
        # Handles all the back buttons based on which part of the Stacked Widget displayed
        currentIndex = self.dlg.stackedWidget.currentIndex()
        if currentIndex == 1:
            # Take the user back to login and clear the text boxes
            self.dlg.stackedWidget.setCurrentIndex(0)
            self.dlg.userlineEdit.clear()
            self.dlg.passwordlineEdit.clear()
            global username
            username = None
            global password
            password = None
        elif currentIndex == 2:
            # Take the user back to where they choose download or upload
            self.dlg.stackedWidget.setCurrentIndex(1)
        elif currentIndex == 3:
            # Take the user back to choosing project-->dataset to download
            self.dlg.stackedWidget.setCurrentIndex(2)
        elif currentIndex == 4:
            # Take the user back to where they choose download or upload
            self.dlg.stackedWidget.setCurrentIndex(1)

    def handleLoginButton(self):
        # Log-In to Strabo -- should work for all user inputs
        global username
        username = self.dlg.userlineEdit.text()
        global password
        password = self.dlg.passwordlineEdit.text()
        # QgsMessageLog.logMessage('username:' + username + " password: " + password)
        url = 'https://strabospot.org/userAuthenticate'
        data = {'email': username, 'password': password}
        headers = {'Content-type': 'application/json', 'Accept-Charset': 'UTF-8'}
        # Later on check for update of Requests library so verify=False can be taken out--
        # --Need to figure out how to accept the StraboSpot SSL Certificate
        r = requests.post(url, json=data, headers=headers, verify= False)
        code = r.status_code
        QgsMessageLog.logMessage('Login Status Code: ' + str(code))
        # Check for a Bad Response- if so, warn the user and reset authorization vars
        if 400 <= code < 500:
            self.iface.messageBar().pushMessage("Error:", "Bad Response: check internet \
                                           connection or make sure to enter email AND \
                                           password.", Qgis.Critical, 10)
            username = None
            password = None
            return
        # If not a Bad Response then check if the user's credentials are a valid account
        response = r.json()
        valid = response['valid']
        QgsMessageLog.logMessage(str(response) + valid)
        QgsMessageLog.logMessage('Response:' + response["valid"])
        # Check the status code for success to move on
        if valid == 'true':
            # If the user is logged-in hide the log in widget and show choose one
            self.dlg.stackedWidget.setCurrentIndex(1)
        elif valid == 'false':
            self.iface.messageBar().pushMessage("Error:", "Login Failed. Try again.", Qgis.Critical, 10)
            username = None
            password = None

    def deploydownloadGUI(self):
        # If the user wants to download a dataset, move to StraboChoose GUI
        self.dlg.stackedWidget.setCurrentIndex(2)

    def getprojects(self, widget_name):
        if widget_name == "create_prj_widget":
            if self.dlg.create_prj_widget.count() > 0:
                self.dlg.create_prj_widget.clear()
        elif widget_name == "projectlistWidget":
            if self.dlg.projectlistWidget.count() > 0:
                self.dlg.projectlistWidget.clear()

        # GET the project list
        url = 'https://strabospot.org/db/myProjects'
        r = requests.get(url, auth=HTTPBasicAuth(username, password), verify=False)
        statuscode = r.status_code
        QgsMessageLog.logMessage(('Get projects code: ' + str(statuscode)))
        response = r.json()
        global projectids
        projectids = []
        # Add project names to projectlistWidget
        for prj in response['projects']:
            if widget_name == "create_prj_widget":
                self.dlg.create_prj_widget.addItem(prj['name'])
            elif widget_name == "projectlistWidget":
                self.dlg.projectlistWidget.addItem(prj['name'])
            projectids.append(prj['id'])

    # Get the project id and then GET the datasets from that project
    # Dataset names are added to the datasetlistWidget
    def getprojectid(self, widget_name):
        global projectname
        if widget_name == "projectlistWidget":
            if self.dlg.datasetlistWidget.count() > 0:
                self.dlg.datasetlistWidget.clear()
            chosenid = self.dlg.projectlistWidget.currentRow()
            projectname = self.dlg.projectlistWidget.currentItem().text()
        elif widget_name == "create_prj_widget":
            chosenid = self.dlg.create_prj_widget.currentRow()
            projectname = self.dlg.create_prj_widget.currentItem().text()

        QgsMessageLog.logMessage('Project Chosen :' + str(projectname) + ' Index of: ' + str(chosenid))
        global projectid
        projectid = projectids[chosenid]

        if widget_name == "projectlistWidget":
            # GET the datasets within a Strabo project
            url = 'https://strabospot.org/db/projectDatasets/' + str(projectid)
            r = requests.get(url, auth=HTTPBasicAuth(username, password), verify=False)
            statuscode = r.status_code
            response = r.json()
            global datasetids
            datasetids = []
            QgsMessageLog.logMessage('Get datasets code: ' + str(statuscode))
            # Add datasets to list widget
            for dataset in response['datasets']:
                self.dlg.datasetlistWidget.addItem(dataset['name'])
                datasetids.append(dataset['id'])

    # Gets the StraboSpot unique identifer for the user-chosen dataset
    # This is needed later for the REST call for the full dataset GeoJSON
    def getdatasetid(self):
        chosenid = self.dlg.datasetlistWidget.currentRow()  # gets the index, corresponds to the datasetids list
        global chosendatasets
        # Gather datasetname and datasetid into a tuple inside a list to be iterated in importSpots
        datasetname = self.dlg.datasetlistWidget.currentItem().text()
        #QgsMessageLog.logMessage('Dataset Chosen :' + str(datasetname) + ' Index of: ' + str(chosenid))
        datasetid = datasetids[chosenid]
        chosendatasets.append([datasetname, datasetid])
        #QgsMessageLog.logMessage('DatasetID: ' + str(datasetid))

    def downloadOptionsGUI(self):
        # Operates the 'Next' Button on the select project/dataset to download GUI
        self.dlg.stackedWidget.setCurrentIndex(3)

    def filebrowse(self):
        self.dlg.dialogPathlineEdit.setText(QFileDialog.getExistingDirectory(None, "Make a new folder here", os.path.expanduser("~"), QFileDialog.ShowDirsOnly))

    def importSpots(self):
        from . import wingdbstub
        """Does most of the work in download process (**==NEEDS WORK)
        **NEEDS TO BE WRITTEN FOR EACH DATASET THAT GETS CHOSEN ONCE IT WORKS FOR ONE...
        1.) **GETs and Saves the GeoJSON for the spots - DONE
        2.) **GETs the images for the dataset if either of the two radio buttons are checked - DONE
            **a. Displays the images in a photo layer.-DONE
        3.) **Puts the GeoJSON into QGIS-- Need to solve the problem with nested arrays - DONE
        4.) **Adds the GeoJSON layers in QGIS to some sort of database? SpatiaLite or PostGIS??"""
        self.dlg.downloadProgresslabel.setText("Retrieving: " + projectname + "\r\n" + "from StraboSpot...")
        self.dlg.downloadprogressBar.setMinimum(0)
        self.dlg.downloadprogressBar.setValue(0)
        self.dlg.downloadprogressBar.setTextVisible(True)
        self.dlg.stackedWidget.setCurrentIndex(4)
        endMessage = ""

        # Set up the folder where files and images will be saved
        prj_nospace = projectname.replace(' ', '')
        prj = prj_nospace.strip()
        directory = self.dlg.dialogPathlineEdit.text()
        projectfolder = prj + datetime.datetime.now().strftime("_%m_%d_%y")
        directory = str.replace(str(directory), "\\", "/")

        datafolder = (str(directory) + '/' + projectfolder)
        if projectfolder in directory:
            datafolder = directory
        else:
            try:
                os.makedirs(datafolder)
            except OSError as exception:
                if exception.errno != errno.EEXIST:
                    raise
                elif exception.errno == errno.EEXIST:  # If the folder does exist
                    # Open file dialog again, prompting the user to make a more specific name
                    self.dlg.dialogPathlineEdit.setText(
                        QFileDialog.getExistingDirectory(None, "Create a new folder.", directory,
                                                         QFileDialog.ShowDirsOnly))
                    datafolder = self.dlg.dialogPathlineEdit.text()
                    # QFileDialog.getExistingDirectory(self, "Make a new folder here", directory, QFileDialog.ShowDirsOnly)
        QgsMessageLog.logMessage("Folder name: " + str(datafolder))
        QgsMessageLog.logMessage(str(directory))
        QgsMessageLog.logMessage(str(datafolder))

        # Using this as a band-aid to get UI events to show up during this loop
        # ideally, this function should be refactored into a seperate thread
        # that updates the GUI using signals/slots so the GUI can update normally.
        QCoreApplication.instance().processEvents()
        # Not sure why we need to run it twice, but we do.
        QCoreApplication.instance().processEvents()

        # GET the project info from StraboSpot and save
        url = 'https://strabospot.org/db/project/' + str(projectid)
        QgsMessageLog.logMessage(url)
        r = requests.get(url, auth=HTTPBasicAuth(username, password), verify=False)
        statuscode = r.status_code
        response = r.json()
        prj_json = response
        rawprojectfile = os.path.join(datafolder, f"{prj}_{str(projectid)}.json")
        # rawprojectfile = datafolder + "\\" + prj + "_" + str(projectid) + ".json"
        tag_spotids = []
        if str(statuscode) == "200" and (not str(prj_json) == 'None'):  # If project is successfully transferred from StraboSpot
            with open(rawprojectfile, 'w') as savedproject:
                json.dump(prj_json, savedproject)
            # Check the project for Tags. Save any spotids to list.
            if 'tags' in prj_json:
                prj_tags = prj_json['tags']
                for tag in prj_tags:
                    if 'spots' in tag:
                        for spot in tag['spots']:
                            tag_spotids.append(spot)

            endMessage = "-StraboSpot Project: " + projectname + " downloaded. \r\n"
            endMessage += "-Data saved in folder: " + datafolder + "\r\n"
            # If selected, create a SpatiaLite or PostGIS database and connect
            if selDB == "SpatiaLite":
                self.dlg.downloadProgresslabel.setText("Creating SpatiaLite Database...")
                SL_conn, SL_cur, db_exists = self.create_spatialite_db(datafolder, prj)
                if db_exists is True:
                    endMessage += "-SpatiaLite Database created.\r\n"
                ''''# testing library versions
                rs = cur.execute('SELECT sqlite_version(), spatialite_version()')
                for row in rs:
                    msg = "> SQLite v%s Spatialite v%s" % (row[0], row[1])
                    QgsMessageLog.logMessage(msg)
                sqlstatement = 'SELECT InitSpatialMetadata()'
                cur.execute(sqlstatement)
                sqlstatement = None'''

            elif selDB == "PostGIS":
                # Add code to create a new PostGIS database
                # Connect to PostGIS (need user and password- will have to pop up a window for input...)
                # Create PostGIS db using this name:
                postDB = os.path.basename(datafolder) + "_" + str(projectid)
                QgsMessageLog.logMessage("PostGIS database to create: " + postDB)
                # Make sure to run the following SQL: "CREATE EXTENSION postgis;"
                # Then use ogr2ogr (Should be included when user does a basic install of QGIS-GDAL tools) to add the geojson
                # files to the db
                # ogr2ogr -f "PostgreSQL" PG:dbname=*postDB* user=postGISUser password=postGISPass" "FULL PATH LOCATION OF JSON FILE"
                # Need to point to C:\\OSGeo4W64\\bin folder to use the above command???
                postGISUser = self.dlg.postgis_userBox_2.text()
                postGISPass = self.dlg.postgis_passBox_2.text()
                postGISport = int(self.dlg.postgis_portBox.text())
                self.dlg.downloadProgresslabel.setText("Creating PostGIS Database...")
                pg_conn, pg_cur, db_exists = self.create_postgres_db(postDB, postGISUser, postGISPass, postGISport)
                if db_exists is True:
                    endMessage += "-PostGIS Database, " + postDB + " created.\r\n"

        progBarMax = len(chosendatasets)
        # Iterate per dataset tuple (dataset's name and id)
        QCoreApplication.instance().processEvents()
        for chosen in chosendatasets:
            datasetname = chosen[0]
            datasetid = chosen[1]
            # GET the datasetspots information from StraboSpot
            url = 'https://strabospot.org/db/datasetspotsarc/' + str(datasetid)
            QgsMessageLog.logMessage(url)
            r = requests.get(url, auth=HTTPBasicAuth(username, password), verify=False)
            statuscode = r.status_code
            response = r.json()

            if str(statuscode) == "200":  # If dataset is successfully transferred from StraboSpot
                # ADD LATER-- FOR EACH DATASET CHOSEN CREATE A "DATASET" FOLDER AND DO THE FOLLOWING
                # Save the datasetspots response to datafolder
                # This whole version of the dataset will be called upon during Upload
                self.dlg.downloadProgresslabel.setText("Downloading: " + datasetname + "\r\n" + "in StraboSpot Project: " + projectname)
                QApplication.instance().processEvents()

                rawjsonfile = os.path.join(datafolder, f"{datasetname}_{str(datasetid)}.json")
                # rawjsonfile = datafolder + "\\" + datasetname + "_" + str(datasetid) + ".json"
                QgsMessageLog.logMessage('JSON file: ' + str(rawjsonfile))
                with open(rawjsonfile, 'w') as savedrawjson:
                    json.dump(response, savedrawjson)

                """Begin Processing the Dataset for use in QGIS: 
                1.) Check dataset for images. If the dataset contains images AND one of the checkboxes
                (.jpeg or .tiff) are checked download the images to the datafolder.
                2.) Parse the raw GeoJSON to make new feature objects out of the nested arrays 
                (i.e. Orientation Data, Samples, Images, etc.) 
                3.) Get the edited JSON file into QGIS using New Vector Layer. 
                4.) (Optional) Make a SpatiaLite database and save each layer file within the database.
                5.) (Optional) Save into a PostGIS database."""

                geometryList = ['point', 'line', 'polygon']
                found_geometry = False
                for geotype in geometryList:
                    url = 'https://strabospot.org/db/datasetspotsarc/' + str(datasetid) + '/' + geotype
                    r = requests.get(url, auth=HTTPBasicAuth(username, password), verify=False)
                    statuscode = r.status_code
                    response = r.json()
                    if str(statuscode) == "200":  # If dataset is successfully transferred from StraboSpot
                        if str(response) == 'None':  # If dataset doesn't have that geometry keep checking
                            continue
                        else:
                            found_geometry = True
                        parsed = response
                        # Set Up and Advance to the Download Progress Widget
                        fullDataset = parsed['features']
                        imageCount = 0
                        for spot in fullDataset:
                            spotprop = spot['properties']
                            if 'images' in spotprop:
                                imgJson = spotprop['images']
                                for img in imgJson:
                                    imageCount += 1
                        QgsMessageLog.logMessage('Images in dataset: ' + str(imageCount))  # Need to work on resizing
                        downloadedimagescount = 0
                        if requestImages is True:
                            # self.dlg.progBarLabel.setText("Preparing to download " + datasetname + " and " + str(imageCount) + " images.") #Need to work on resizing
                            progBarMax += imageCount  # each downloaded image + (parsing GeoJSON, create layer, save layer(s) to db)
                            self.dlg.imageprogLabel.setText(
                                "Image " + str(downloadedimagescount) + " of " + str(imageCount) + " downloaded.")
                            imgFolder = os.path.join(datafolder, f"{datasetname}_Images")
                            try:
                                os.makedirs(imgFolder)
                            except OSError as exception:
                                if exception.errno != errno.EEXIST:
                                    raise
                                elif exception.errno == errno.EEXIST:  # If the folder does exist then store in project folder
                                    imgFolder = datafolder
                            # Initialize Json for making an images layer
                            imagesJson = []

                        progBarMax += 2  # parsing GeoJSON, create layer, save layer(s) to db (Perhaps this should be Spot#?)
                        self.dlg.downloadprogressBar.setMaximum(progBarMax)

                        # Iterate Spots to reorganize nested arrays and download images
                        newDatasetJson = []
                        for spot in fullDataset:
                            # Gather basic information on the Spot
                            spotgeometry = spot['geometry']
                            spotprop = spot['properties']
                            spotID = spotprop['id']
                            spotModTS = spotprop['modified_timestamp']
                            spottime = spotprop['time']
                            spotdate = spotprop['date']
                            spotself = spotprop['self']
                            newSpot = {}
                            newSpot['type'] = 'Feature'
                            newSpot['geometry'] = spotgeometry
                            newSpot['properties'] = {'id': spotID, 'modified_timestamp': spotModTS,
                                                     'time': spottime, 'date': spotdate, 'self': spotself}
                            newDatasetJson.append(newSpot)
                            # Check if the Spot is associated with any Tags from the project JSON
                            if spotID in tag_spotids:
                                for tag in prj_tags:
                                    if 'spots' in tag:
                                        if spotID in tag['spots']:
                                            QgsMessageLog.logMessage("Tag associated with spotID" + str(spotID))
                                            newTag = {}
                                            newTag['type'] = 'Feature'
                                            newTag['geometry'] = spotgeometry
                                            newTag['properties'] = {}
                                            for key in tag:
                                                if not key == 'spots':
                                                    newfield = 'tag_' + key  # To avoid table confusion
                                                    newTag['properties'][newfield] = tag.get(key)
                                            newDatasetJson.append(newTag)
                            # Check for and add special features (nested JSON arrays)
                            if 'orientation_data' in spotprop:
                                # Handle orientation data
                                ori_dataJson = spotprop['orientation_data']
                                for ori_data in ori_dataJson:  # Each set of measurements in the Orientation Data array
                                    newOri = {}
                                    newOri['type'] = 'Feature'
                                    newOri['geometry'] = spotgeometry
                                    newOri['properties'] = {}
                                    for key in ori_data:
                                        key = key + "_orientation_data"
                                        newOri['properties'][key] = ori_data.get(key)
                                    newOri['properties']['SpotID'] = spotID
                                    newDatasetJson.append(newOri)
                            if 'rock_unit' in spotprop:
                                # Handle rock unit data
                                rock_unitJson = spotprop['rock_unit']
                                newRockUnit = {}
                                newRockUnit['type'] = 'Feature'
                                newRockUnit['geometry'] = spotgeometry
                                newRockUnit['properties'] = {}
                                for key in rock_unitJson:
                                    key = key + "_rock_unit"
                                    newRockUnit['properties'][key] = rock_unitJson.get(key)
                                newRockUnit['properties']['SpotID'] = spotID
                                newDatasetJson.append(newRockUnit)
                            if 'trace' in spotprop:
                                # Handle trace data
                                traceJson = spotprop['trace']
                                newTrace = {}
                                newTrace['type'] = 'Feature'
                                newTrace['geometry'] = spotgeometry
                                newTrace['properties'] = {}
                                for key in traceJson:
                                    key = key + "_trace"
                                    newTrace['properties'][key] = traceJson.get(key)
                                newTrace['properties']['SpotID'] = spotID
                                newDatasetJson.append(newTrace)

                            if 'samples' in spotprop:
                                # Handle samples data
                                samplesJson = spotprop['samples']
                                for samples_data in samplesJson:
                                    newSample = {}
                                    newSample['type'] = 'Feature'
                                    newSample['geometry'] = spotgeometry
                                    newSample['properties'] = {}
                                    for key in samples_data:
                                        key = key + "_samples"
                                        newSample['properties'][key] = samples_data.get(key)
                                    newSample['properties']['SpotID'] = spotID
                                    newDatasetJson.append(newSample)

                            if '_3d_structures' in spotprop:
                                _3DJson = spotprop['3d_structures']
                                for _3d in _3DJson:
                                    new3d = {}
                                    new3d['type'] = 'Feature'
                                    new3d['geometry'] = spotgeometry
                                    new3d['properties'] = {}
                                    for key in _3DJson:
                                        key = key + "_3d_structures"
                                        new3d['properties'][key] = _3d.get(key)
                                    new3d['properties']['SpotID'] = spotID
                                    newDatasetJson.append(new3d)

                            if 'other_features' in spotprop:
                                otherFeatJson = spotprop['other_features']
                                for otherFeat in otherFeatJson:
                                    newOther = {}
                                    newOther['type'] = 'Feature'
                                    newOther['geometry'] = spotgeometry
                                    newOther['properties'] = {}
                                    for key in otherFeat:
                                        key = key + "_other_features"
                                        newOther['properties'][key] = otherFeat.get(key)
                                    newOther['properties']['SpotID'] = spotID
                                    newDatasetJson.append(otherFeat)

                            if 'images' in spotprop:
                                imgJson = spotprop['images']
                                for img in imgJson:
                                    newImg = {}
                                    newImg['type'] = 'Feature'
                                    newImg['geometry'] = spotgeometry
                                    newImg['properties'] = {}
                                    for key in img:
                                        key = key + "_images"
                                        newImg['properties'][key] = img.get(key)
                                    newImg['properties']['SpotID'] = spotID
                                    # Save the actual image to disk
                                    imgURL = img.get('self')
                                    imgID = img.get('id')
                                    # QgsMessageLog.logMessage(imgURL)
                                    # If the user requested images be downloaded, retrieve image from StraboSpot
                                    if requestImages is True:
                                        downloadedimagescount += 1
                                        r = requests.get(imgURL, auth=HTTPBasicAuth(username, password), verify=False, stream=True)
                                        statuscode = r.status_code
                                        #QgsMessageLog.logMessage(imgURL + " accessed with status code " + str(statuscode))
                                        # If the image was successfully retrieved from StraboSpot, save to file and geoTag
                                        if str(statuscode) == '200':
                                            imgFile = imgFolder + "/" + str(imgID) + fileExte
                                            with open(imgFile, 'wb') as f:
                                                r.raw.decode_content = True
                                                shutil.copyfileobj(r.raw, f)
                                            if fileExte == ".jpeg":
                                                self.geotag_photos(spotgeometry, imgFile, geotype)
                                        elif str(statuscode) == '404':
                                            warningMsg = "Image with id: " + str(imgID) + " not downloaded. Click 'Ok' to continue downloading."
                                            result = QMessageBox.warning(None, "Error", warningMsg, QMessageBox.Ok)

                                        self.dlg.downloadprogressBar.setValue(downloadedimagescount)
                                        self.dlg.imageprogLabel.setText(
                                            "Image " + str(downloadedimagescount) + " of " + str(imageCount) + " successfully downloaded.")

                                        QApplication.instance().processEvents()
                                        newImg['properties']['path'] = imgFile
                                        imagesJson.append(newImg)
                                    newDatasetJson.append(newImg)
                        # Convert to GeoJson Array
                        fullJson = {'type': 'FeatureCollection',
                                    'features': newDatasetJson}
                        modifiedJson = json.dumps(fullJson)
                        # Save newly organized GeoJson array to file
                        modifiedFileName = os.path.join(datafolder,
                                                        f"{datasetname}_{geotype}_{str(datasetid)}.geojson")
                        # modifiedFileName = datafolder + "\\" + datasetname + "_" + geotype + "_" + str(datasetid) + ".geojson"
                        modifiedFileName = str.replace(str(modifiedFileName), "\\", "/")
                        modifiedJsonDict = json.loads(modifiedJson)
                        QgsMessageLog.logMessage('Modifided Json file: ' + modifiedFileName)
                        with open(modifiedFileName, 'w') as savemodJson:
                            json.dump(modifiedJsonDict, savemodJson)

                        self.dlg.downloadprogressBar.setValue(self.dlg.downloadprogressBar.value() + 1)
                        self.dlg.progBarLabel.setText("Creating QGIS layer of name: " + datasetname + "...")
                        QApplication.instance().processEvents()

                        # Add the modified Json file as a QGIS Layer
                        layername = datasetname + "_" + geotype
                        newlayer = QgsVectorLayer(modifiedFileName, layername, "ogr")
                        if not newlayer.isValid():
                            QgsMessageLog.logMessage("Layer: " + layername + " is not valid...")
                        else:
                            self._qgs_project.addMapLayer(newlayer)
                            # Try Adding the project info to the metadata for upload...
                            # Add to databases

                            if selDB == "SpatiaLite":
                                self.dlg.progBarLabel.setText("Saving QGIS layer to " + selDB + " database")
                                table_exists = self.create_spatialite_table(newlayer, newDatasetJson, geotype, SL_conn, SL_cur)
                                if table_exists is True:
                                    endMessage += "-SpatiaLite table for " + newlayer.name() + " successfully created.\r\n"
                                else:
                                    endMessage += "-Error creating SpatiaLite table, " + newlayer.name() + ", see Message Log for details."

                            elif selDB == "PostGIS":
                                self.dlg.progBarLabel.setText("Saving QGIS layer to " + selDB + " database")
                                endMessage += "-GeoJSON for " + datasetname + " " + geotype + " saved.\r\n"
                                resultBool = self.load_geojson_to_postgis(postDB, postGISUser, postGISPass, postGISport, modifiedFileName)
                                if resultBool is True:
                                    endMessage += "-PostGIS table for " + datasetname + "_" + geotype + " saved in " + postDB + " database.\r\n"
                                if resultBool is False:
                                    endMessage += "-Error creating PostGIS table for, " + datasetname + "_" + geotype + ", see Message Log for details."

                        self.dlg.downloadprogressBar.setValue(self.dlg.downloadprogressBar.value() + 1)
                        QApplication.instance().processEvents()

                        if requestImages is True and (not imagesJson == []):
                            allImagesJson = {'type': 'FeatureCollection',
                                             'features': imagesJson}
                            fullimgJson = json.dumps(allImagesJson)
                            imageLayer = datasetname + "_" + geotype + "_images"
                            newimagelayer = QgsVectorLayer(fullimgJson, imageLayer, "ogr")
                            '''The following line sets the HTML MapTip Display Text under Layer Properties-> Display tab
                                From pg. 299 QGIS Pyton Programming Cookbook and 
                                https://gis.stackexchange.com/questions/123675/how-to-get-image-pop-ups-in-qgis
                                But in QGIS 3.0 can use 'setMapTipTemplate' 
                                Be sure in informational videos to tell user where to edit the HTML!'''
                            newimagelayer.setDisplayField('<b> Image ID: </b> [% "id" %] <br> <img src ="[% "path" %]" width=400 height=400/>')
                            if not newimagelayer.isValid():
                                QgsMessageLog.logMessage("Image layer is not valid...")
                            else:
                                self._qgs_project.addMapLayer(newimagelayer)

                        self.dlg.downloadprogressBar.setValue(self.dlg.downloadprogressBar.value() + 1)
                        QApplication.instance().processEvents()
                        if self.dlg.downloadprogressBar.value() == self.dlg.downloadprogressBar.maximum():
                            self.dlg.close()
                if found_geometry:
                    endMessage += "-StraboSpot Dataset, " + chosen[0] + ", successfully downloaded.\r\n"
                else:
                    endMessage += f"-StraboSpot Dataset, {chosen[0]} ERROR: No geometries found!\r\n"
                    self.dlg.close()

            else:
                errorMsg = "Dataset, " + datasetname + ", could not be downloaded from StraboSpot."
                result = QMessageBox.critical(None, "Critical Error", errorMsg, QMessageBox.Ok)
        if selDB == "SpatiaLite":
            SL_conn.commit()
            SL_conn.close()
        # elif selDB == "PostGIS":

        # Notify user of what was downloaded and created
        QMessageBox.information(None, "Download Complete", endMessage, QMessageBox.Ok)

    def setJpeg(self):
        global fileExte
        fileExte = ".jpeg"
        QgsMessageLog.logMessage("JPEG Images")
        global requestImages
        requestImages = True

    def setTiff(self):
        global fileExte
        fileExte = ".tiff"
        QgsMessageLog.logMessage("TIFF Images")
        global requestImages
        requestImages = True

    def setPostGIS(self):
        global selDB
        selDB = "PostGIS"

    def setSpatiaLite(self):
        global selDB
        selDB = "SpatiaLite"

    def geotag_photos(self, spotgeo, imageName, geoType):
        """Based off guidance: from https://stackoverflow.com/questions/44636152/how-to-modify-exif-data-in-python
        and Issues documentation at https://github.com/hMatoba/Piexif
        KeyError handling from: https://github.com/getnikola/nikola/blob/master/nikola/image_processing.py"""

        # Open image and try to get Exif dictionary
        ImageFile.LOAD_TRUNCATED_IMAGES = True
        coordinates = spotgeo['coordinates']
        savedImg = Image.open(imageName)
        try:
            exif_dict = piexif.load(savedImg.info['exif'])
        except KeyError:
            exif_dict = None

        if exif_dict is not None:
            # Get the lat/long info
            if geoType == "point":
                longitude = coordinates[0]
                latitude = coordinates[1]
            # Can only store one lat/long pair to Exif, so pull the first set of coordinates
            if geoType == "line":
                longitude = coordinates[0][0]
                latitude = coordinates[0][1]
            if geoType == "polygon":
                longitude = coordinates[0][0][0]
                latitude = coordinates[0][0][1]

            # Set Long/Lat Exif Refs
            if longitude < 0:
                exif_dict['GPS'][piexif.GPSIFD.GPSLongitudeRef] = "W"
            else:
                exif_dict['GPS'][piexif.GPSIFD.GPSLongitudeRef] = "E"
            if latitude < 0:
                exif_dict['GPS'][piexif.GPSIFD.GPSLatitudeRef] = "S"
            else:
                exif_dict['GPS'][piexif.GPSIFD.GPSLatitudeRef] = "N"

            # Convert from decimal degrees to degrees, minutes, seconds
            # Longitude
            temp_val = abs(longitude)
            long_deg = math.trunc(temp_val)
            temp_val = ((temp_val - long_deg) * 60)
            long_mins = math.trunc(temp_val)
            temp_val = ((temp_val - long_mins) * 60)
            long_sec = math.trunc(temp_val * 1000)

            QgsMessageLog.logMessage("Long DMS: " + str(long_deg) + "," + str(long_mins) + "," + str(long_sec))
            # Latitude
            temp_val = abs(latitude)
            lat_deg = math.trunc(temp_val)
            temp_val = ((temp_val - lat_deg) * 60)
            lat_mins = math.trunc(temp_val)
            temp_val = ((temp_val - lat_mins) * 60)
            lat_sec = math.trunc(temp_val * 1000)

            QgsMessageLog.logMessage("Lat DMS: " + str(lat_deg) + "," + str(lat_mins) + "," + str(lat_sec))
            # Save info to Exif
            exif_dict['GPS'][piexif.GPSIFD.GPSLongitude] = [(int(long_deg), 1), (int(long_mins), 1), (long_sec, 1000)]
            exif_dict['GPS'][piexif.GPSIFD.GPSLatitude] = [(int(lat_deg), 1), (int(lat_mins), 1), (lat_sec, 1000)]
            # Save edited Exif to Image
            exif_bytes = piexif.dump(exif_dict)
            savedImg.save(imageName, "jpeg", exif=exif_bytes)
        else:
            warningMsg = "Image file: \n" + imageName + "\n could not be geotagged. Click 'Ok' to continue downloading."
            result = QMessageBox.warning(None, "Error", warningMsg, QMessageBox.Ok)

    def create_spatialite_db(self, folderpath, project_name):
        # Create/Connect to the database
        slDB = os.path.join(folderpath,
                            f'{project_name}{datetime.datetime.now().strftime("_%m-%d-%y")}.sqlite')
        # slDB = folderpath + "\\" + project_name + datetime.datetime.now().strftime("_%m-%d-%y") + ".sqlite"
        dbconnection = spatialite_connect(slDB)
        uri = QgsDataSourceUri()
        uri.setDatabase(slDB)
        dbcursor = dbconnection.cursor()
        sqlstatement = "SELECT InitSpatialMetadata(1)"
        try:
            dbcursor.execute(sqlstatement)
        except db.Error as exe_error:
            QgsMessageLog.logMessage("Error creating SpatiaLite Table: " + exe_error)
            return dbconnection, dbcursor, False
        dbconnection.commit()

        return dbconnection, dbcursor, True

    def create_spatialite_table(self, qgislayer, layerjson, geometrytype, dbconnection, dbcursor):
        fields = []
        layername = qgislayer.name()
        exe_error = ""

        for field in qgislayer.pendingFields():
            fieldtype = field.typeName()
            if fieldtype == "String":
                fieldtype = 'Text'
            elif fieldtype == "Integer64":
                fieldtype = 'BIGINT'
            elif fieldtype == "DateTime":
                fieldtype = "TIMESTAMP"
            if field.name() == 'id':
                fieldtype = "PRIMARY KEY"

            fields.append(field.name() + " " + fieldtype)
        # https://www.gaia-gis.it/spatialite-2.4.0-4/splite-python.html
        # Create the table using the list of fields and field types
        sqlstatement = "CREATE TABLE IF NOT EXISTS " + layername + "(" + ",".join(fields) + ");"
        QgsMessageLog.logMessage(sqlstatement)
        try:
            dbcursor.execute(sqlstatement)
        except db.Error as exe_error:
            QgsMessageLog.logMessage("Error creating SpatiaLite Table: " + exe_error)
            return False

        dbconnection.commit()
        # Add a geometry column to the table
        if geometrytype == 'line':
            tablegeo = 'linestring'
        else:
            tablegeo = geometrytype

        # Add a column for the geometry- cannot be combined with create table sql above!
        sqlstatement = "SELECT AddGeometryColumn('" + layername + "', 'geom', 4326," + "'" + tablegeo.capitalize() + "', 'XY');"
        QgsMessageLog.logMessage(sqlstatement)
        try:
            dbcursor.execute(sqlstatement)
        except db.Error as exe_error:
            QgsMessageLog.logMessage("Error Adding Geometry Column to SpatiaLite Table: " + exe_error)
            return False
        dbconnection.commit()

        # Add rows to table using the geojson from saving the layer:
        for spot in layerjson:
            spotkeys = []
            spotvals = []
            spotgeom = spot['geometry']
            spotprop = spot['properties']
            for kvp in spotprop:
                spotkeys.append(kvp)
                valuetoadd = spotprop.get(kvp)
                if isinstance(valuetoadd, bool):  # Catch boolean values and convert to int
                    if str(valuetoadd) == 'false':
                        spotvals.append(0)
                    else:
                        spotvals.append(1)
                elif isinstance(valuetoadd, int) or isinstance(valuetoadd, float) \
                        or isinstance(valuetoadd, long):
                    spotvals.append(valuetoadd)
                elif valuetoadd is None:  # Take care of Null values
                    spotvals.append("NULL")
                else:  # Everything else *should* be a string, so quote it
                    spotvals.append("'" + valuetoadd + "'")
            spotkeys.append('geom')
            # Construct the geometry JSON object to add to the table... Be sure to test this with LineString and Polygon!!!!!!!!
            strgeom = str(spotgeom['coordinates'])
            modgeom = '{"type": ' + '"' + tablegeo.capitalize() + '"' + \
                      ',"crs":{"type":"name","properties":{"name":"EPSG:4326"}},"coordinates":' + \
                      strgeom + '}'
            # Execute SQL statement inserting the row
            keys = ",".join(spotkeys)
            vals = ",".join([unicode(i) for i in spotvals])
            sqlstatement = "INSERT INTO " + layername + "(" + keys + ") VALUES " + "(" + vals + ",GeomFromGeoJSON('" + modgeom + "'))"
            QgsMessageLog.logMessage(json.dumps(modgeom))

            QgsMessageLog.logMessage(sqlstatement)
            try:
                dbcursor.execute(sqlstatement)
            except db.Error as exe_error:
                QgsMessageLog.logMessage("Error populating SpatiaLite table: " + exe_error)
                return False

            dbconnection.commit()
            return True  # No errors detected, so table was successfully created

    def create_postgres_db(self, db_name, postgis_user, postgis_pass, postgis_port):
        # Following advice from Stackexchange question: https://stackoverflow.com/questions/19426448/creating-a-postgresql-db-using-psycopg2
        # https://stackoverflow.com/questions/34484066/create-a-postgres-database-using-python/34484185
        # https://hub.packtpub.com/moving-spatial-data-one-format-another/
        # Connect to the main 'postgres' database
        dbconn = psycopg2.connect(host='localhost', port= postgis_port, database='postgres', user= postgis_user, password=postgis_pass)
        dbconn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        dbcur = dbconn.cursor()
        # Run SQL command to create a new db
        #sqlcmd = """CREATE DATABASE %s"""
        # "WITH OWNER = " + postgis_user + \
        # " ENCODING = 'UTF8' LC_COLLATE = 'English_United States.1252' LC_CTYPE = 'English_United States.1252'" + \
        #  " TABLESPACE = pg_default CONNECTION LIMIT = -1;"
        dbcur.execute("CREATE DATABASE %s ;" % db_name)
        dbconn.commit()
        dbconn.close()
        dbconn = psycopg2.connect(host='localhost', port=postgis_port, database=db_name.lower(), user=postgis_user, password=postgis_pass)
        dbcur = dbconn.cursor()
        dbcur.execute("CREATE EXTENSION postgis;")
        dbconn.commit()

        # Add the PostgreSQL database connection to QGIS
        # pg. 91 "The PyGIS Programmer's Guide" By: Garry Sherman
        qgisConn = QSqlDatabase.addDatabase('QPSQL')
        QgsMessageLog.logMessage("QPSQL db is value: " + str(qgisConn.isValid()))
        if qgisConn.isValid():
            qgisConn.setHostName('localhost')
            qgisConn.setDatabaseName(db_name.lower())
            qgisConn.setPort(postgis_port)
            qgisConn.setUserName(postgis_user)
            qgisConn.setPassword(postgis_pass)
            if qgisConn.open():
                QgsMessageLog.logMessage("Successfully connected to PostGIS db: " + db_name.lower())
                postgis_exists = True
                # Add to canvas
                qgisURI = QgsDataSourceUri()
                qgisURI.setConnection('localhost', str(postgis_port), db_name.lower(), postgis_user, postgis_pass)

            else:
                err = qgisConn.lastError()
                postgis_exists = False
                QgsMessageLog.logMessage("Error connecting to PostGIS db: " + db_name.lower() + "- " + err.driverText())
        return dbconn, dbcur, postgis_exists

    def load_geojson_to_postgis(self, db_name, postgis_user, postgis_pass, postgis_port, json_file):
        # ogr2ogr -f "PostgreSQL" PG:dbname=*postDB* user=postGISUser password=postGISPass" "FULL PATH LOCATION OF JSON FILE"
        gdal.UseExceptions()
        pgconn = "PG:host=localhost port=" + str(postgis_port) + " user='" + postgis_user + "' password='" + postgis_pass + "' dbname='" + db_name.lower() + "'"
        # subprocess.call(["ogr2ogr", "-f", "PostgreSQL", pgconn, json_file])
        # Using VectorTranslate to load the geojson into the PostGIS table from this post:
        # https://svn.osgeo.org/gdal/trunk/autotest/utilities/test_ogr2ogr_lib.py
        result = gdal.VectorTranslate(pgconn, json_file, format='PostgreSQL')
        # Check the result- http://svn.osgeo.org/gdal/trunk/autotest/utilities/test_ogr2ogr_lib.py
        lyr = result.GetLayer(0)
        if lyr.GetFeatureCount() > 0:
            return True
        else:
            return False

        # Might want to add the database connection to DB Manager- doesn't seem to be a good way of accomplishing this
        # Possible leads: https://gis.stackexchange.com/questions/269412/qgis-splitvectorlayer-wrong-output-directory
        # (Do the same thing they did for Processing Plug-In for the db_manager plug-in?? then use PostGisDBConnector?
        # https://gis.stackexchange.com/questions/180427/retrieve-available-postgis-connections-in-pyqgis
        # https://lists.osgeo.org/pipermail/qgis-developer/2015-October/040059.html
        # Or manipulating the DB Manager through QSettings? http://pyqt.sourceforge.net/Docs/PyQt4/pyqt_qsettings.html

    # Upload Functions
    def deployuploadGUI(self):
        # If the user wants to upload a dataset, move to uploadDatasets GUI
        # Add open QGIS layer names to the list box
        if self.dlg.qgislayers.count() > 0:
            self.dlg.qgislayers.clear()

        # Add current open layers to list of upload choices
        if self._qgs_project.count() > 0:
            sel_layers_tup = (self.iface.mapCanvas().layers())
            # for layer in QgsMapLayerRegistry.instance().mapLayers().values():
            # sel_layers_list.append(layer.name())
        else:
            warningMsg = "No open layers detected. \r\n" \
                         "Please close the StraboSpot Plug-In, open the layers to upload, and try again. "
            QMessageBox.warning(None, "Error", warningMsg, QMessageBox.Ok)
        # To add the layers in the same order as they are in the table of contents
        # sel_layers_list.reverse()
        for lyr in sel_layers_tup:
            self.dlg.qgislayers.addItem(lyr.name())
        # Advance to the page for user interaction
        self.dlg.stackedWidget.setCurrentIndex(5)

    def chosen_layers(self):
        # Returns QGIS layer names to "overwrite_datasets_options" which the user wants uploaded to StraboSpot
        global upload_layer_list
        layer_index = self.dlg.qgislayers.currentRow()
        layer_name = self.dlg.qgislayers.currentItem().text()
        upload_layer_list.append([layer_name, layer_index])

    def set_overwrite(self):
        global sel_upload_method
        sel_upload_method = "Overwrite"
        self.dlg.stackedWidget.setCurrentIndex(6)

    def set_create(self):
        global sel_upload_method
        sel_upload_method = "Create"
        self.dlg.upload_confirm_lbl.setText("Create New StraboSpot Dataset(s)")
        self.dlg.confirm_items_lbl.setText("Select Project to upload layer(s)...")
        # Get all user's projects
        self.getprojects("create_prj_widget")
        self.dlg.stackedWidget.setCurrentIndex(6)

    def setup_upload_confirm(self):
        # 'Choose Layers' Button on upload method page sets up the rest of the page
        # This is based on which option for upload the user chose:
        # Update Existing StraboSpot Dataset OR Create New StraboSpot Dataset

        if sel_upload_method == "Overwrite":  # the user wants to overwrite an existing StraboSpot dataset
            # Add label stuff
            self.dlg.upload_confirm_lbl.setText("Overwrite dataset(s) in StraboSpot")
            self.dlg.confirm_items_lbl.setText("Layers to upload...")
            for lyr in upload_layer_list:

                # Set up vars
                strabo_project_name = ""
                strabo_dataset_name = ""
                strabo_project_id = ""
                strabo_dataset_id = ""
                # Get the layer object
                lyr_index = int(lyr[1])
                selected_layer = self.iface.mapCanvas().layer(lyr_index)
                # Gather StraboSpot info about the layer
                if str(lyr[0]) == selected_layer.name():
                    data_provider = selected_layer.source()
                    provider_type = selected_layer.providerType()
                    QgsMessageLog.logMessage(
                        "Data Provider for " + lyr[0] + " is " + data_provider + " from " + provider_type)
                    if provider_type == "spatialite" or provider_type == "postgres":  # If Sqlite layer or PostGIS
                        provider_list = data_provider.split(" ")
                        for kvp in provider_list:
                            if kvp.startswith("dbname"):
                                db_source = kvp.split("=")[1][1:-1]
                            elif kvp.startswith("table"):
                                db_table = kvp.split("=")[1][1:-1]

                    else:  # If its just a QGIS Vector Layer
                        db_source = data_provider

                    if provider_type == "spatialite" or db_source.endswith(".geojson"):
                        basefolder, basefile = os.path.split(db_source)
                        if provider_type == "spatialite":
                            strabo_project_name = basefile.split("_")[0]
                            QgsMessageLog.logMessage("SpatiaLite Project name: " + strabo_project_name)
                        else:
                            strabo_project_name = os.path.basename(basefolder).split("_")[0]
                        for fname in os.listdir(basefolder):
                            if fname.startswith(strabo_project_name) and fname.endswith(".json"):
                                QgsMessageLog.logMessage("Project file: " + fname)
                                strabo_project_id = fname.split("_")[1].strip(".json")
                                QgsMessageLog.logMessage("SpatiaLite project ID: " + strabo_project_id)
                            elif fname.lower().startswith(selected_layer.name().lower().split("_")[0]) and fname.endswith(".json"):
                                strabo_dataset_id = (fname.split("_")[-1]).strip(".json")
                                strabo_dataset_name = fname.split("_")[0]
                                QgsMessageLog.logMessage(
                                    "Strabo Dataset: " + strabo_dataset_name + " " + strabo_dataset_id)
                    elif provider_type == "postgres":  # PostGIS database
                        strabo_project_id = db_source.split("_")[-1]
                        strabo_project_name = db_source.split("_")[0]
                        strabo_dataset_id = db_table.split("_")[-1]
                        strabo_dataset_name = (db_table.split("_")[0]).strip('public"."')
                        QgsMessageLog.logMessage("Project: " + strabo_project_name + " " + strabo_project_id)
                        QgsMessageLog.logMessage("Dataset: " + strabo_dataset_name + " " + strabo_dataset_id)

                # Add info to the list widget
                self.dlg.create_prj_widget.addItem(selected_layer.name())
                self.dlg.create_prj_widget.addItem("Project: " + strabo_project_name)
                self.dlg.create_prj_widget.addItem("Dataset: " + strabo_dataset_name)

                # Add info to the list in the tuple
                upload_layer_list[lyr].append(strabo_dataset_id)

        # No matter the upload method, convert each layer to GeoJSON
        for lyr in upload_layer_list:
            # Create a temp folder/file for layer GeoJSON files
            global temp_folder
            handle, tmpfile = mkstemp(suffix='.geojson')
            temp_folder = handle
            os.close(handle)
            crs = QgsCoordinateReferenceSystem(4326)

            # Get the layer object
            lyr_index = int(lyr[1])
            selected_layer = self.iface.mapCanvas().layer(lyr_index)
            # Gather StraboSpot info about the layer
            if str(lyr[0]) == selected_layer.name():
                # Convert layer to GeoJSON
                # From Pg. 375 of QGIS Python Programming Cookbook; By: Joel Lawhead; accessed through GoogleBooks
                error = QgsVectorFileWriter.writeAsVectorFormat(selected_layer, tmpfile, "utf-8",
                                                                crs, "GeoJSON", onlySelected=False)
                if error != QgsVectorFileWriter.NoError:
                    QgsMessageLog.logMessage("Layer: " + selected_layer.name() + " could not be converted to GeoJSON and will not be uploaded.")

    def upload_dataset(self):
        self.dlg.stackedWidget.setCurrentIndex(7)
        # Overwrite Current Dataset
        if sel_upload_method == "Overwrite":
            # Go through the process to signal to StraboSpot to save a Version of the project
            # Get project json
            url = 'https://strabospot.org/db/project/' + projectid
            r = requests.get(url, auth=HTTPBasicAuth(username, password), verify=False)
            statuscode = r.status_code
            QgsMessageLog.logMessage(('Get projects code: ' + str(statuscode)))
            response = r.json()
            # Update modified timestamp
            response['modified_timestamp'] = int(time.time())
            QgsMessageLog.logMessage("Modified Response: " + response)

            # Post Modified Project JSON to StraboSpot
            url = 'https://strabospot.org/db/project/' + projectid
            headers = {'Content-type': 'application/json', 'Accept-Charset': 'UTF-8'}
            r = requests.post(url, auth=HTTPBasicAuth(username, password), headers=headers, json=response, verify=False)
            statuscode = r.status_code
            QgsMessageLog.logMessage(('Post project code: ' + str(statuscode)))

            # Iterate the Layers to Upload
            for lyr in upload_layer_list:
                datasetid = lyr[2]
                # Get All Spots in the dataset the layer is associated with
                url = 'https://strabospot.org/db/datasetspots/' + str(datasetid)
                r = requests.get(url, auth=HTTPBasicAuth(username, password), verify=False)
                statuscode = r.status_code
                response = r.json()
                if str(statuscode) == "200":
                    dataset_spots = response['features']  # This will later be compared to the geojson from the lyr

                    # Get the StraboSpot dataset JSON
                    url = 'https://strabospot.org/db/dataset/' + str(datasetid)
                    r = requests.get(url, auth=HTTPBasicAuth(username, password), verify=False)
                    statuscode = r.status_code
                    response = r.json()
                    if str(statuscode) == "200":
                        response['modified_timestamp'] = time.time()

                    # Update the StraboSpot dataset JSON
                    url = 'https://strabospot.org/db/dataset/' + str(datasetid)
                    headers = {'Content-type': 'application/json', 'Accept-Charset': 'UTF-8'}
                    r = requests.post(url, auth=HTTPBasicAuth(username, password), headers=headers, json=response, verify=False)
                    statuscode = r.status_code
                    QgsMessageLog.logMessage(('Post project code: ' + str(statuscode)))

                    for temp in gettempdir():  # read the files in the current temp directory
                        QgsMessageLog.logMessage(temp)
        elif sel_upload_method == "Create":
            # Choose dataset
            # Choose project to add it to
            # Create new strabo dataset and add to project
            # Get layer GeoJSON, parse to morph spots (same IDs), use it to populate new dataset
            for lyr in upload_layer_list:
                #unixTime = int(round((datetime.datetime.utcnow() - datetime.datetime(1970, 1, 1)).total_seconds() * 1000))
                # unixTime logic based on 3rd answer from here: https://stackoverflow.com/questions/5998245/get-current-time-in-milliseconds-in-python?noredirect=1&lq=1
                unixTime = int(time.time())
                randInt = int(numpy.random.random())
                timeStamp = str(unixTime) + str(randInt)

                new_dataset_json = {"id": timeStamp, "name": lyr[0],
                                    "modified_timestamp": unixTime, "date": datetime.datetime.utcnow()}
                datasetid = lyr[2]
                url = 'https://strabospot.org/db/dataset/' + str(datasetid)
                headers = {'Content-type': 'application/json', 'Accept-Charset': 'UTF-8'}
                r = requests.post(url, auth=HTTPBasicAuth(username, password), headers=headers, json=new_dataset_json,
                                  verify=False)
                statuscode = r.status_code

    def run(self):
        """Run method that performs all the real work"""
        # show the dialog
        self.dlg.show()
