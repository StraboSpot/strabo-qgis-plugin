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
"""
from PyQt4.QtCore import QSettings, QTranslator, qVersion, QCoreApplication
from PyQt4.QtGui import *
from qgis.core import QgsMessageLog, QgsMapLayerRegistry, QgsVectorLayer
from qgis.gui import QgsMessageBar
import qgis.utils
# Initialize Qt resources from file resources.py
import resources
# Import the code for the dialog
from strabo_spot_dialog import StraboSpotDialog
import os.path
import requests
from requests.auth import HTTPBasicAuth
import json
import errno
import datetime
import shutil
import piexif
from PIL import Image
from PIL import ImageFile
import numpy

class StraboSpot:
    """QGIS Plugin Implementation."""
    #These are global variables
    global username, password, projectid, datasetid, projectids, datasetids, projectname, datasetname, requestImages, fileExte
    username= None
    password= None
    projectid = None
    datasetid = None
    projectids = []
    datasetids = []
    projectname = None
    datasetname = None
    requestImages = False
    fileExte = None
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
        self.dlg.getProjectspushButton.clicked.connect(self.getprojects)
        self.dlg.projectlistWidget.itemClicked.connect(self.getprojectid)
        self.dlg.datasetlistWidget.itemClicked.connect(self.getdatasetid)
        self.dlg.toOptionspushButton.clicked.connect(self.downloadOptionsGUI)
        self.dlg.downloadradioButton.clicked.connect(self.deploydownloadGUI)
        self.dlg.uploadradioButton.clicked.connect(self.deployuploadGUI)
        self.dlg.browsepushButton.clicked.connect(self.filebrowse)
        self.dlg.importpushButton.clicked.connect(self.importSpots)
        self.dlg.jpegradioButton.clicked.connect(self.setJpeg)
        self.dlg.tiffradioButton.clicked.connect(self.setTiff)

        # Set up the Message Bar in QGIS for showing the user errors
        self.bar = QgsMessageBar()
        self.dlg.websitelabel.setText('<a href="https://strabospot.org">Visit StraboSpot</a>')
        self.dlg.websitelabel.setOpenExternalLinks(True)

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
            #Take the user back to login and clear the text boxes
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
        elif currentIndex ==4:
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
        #Later on check for update of Requests library so verify=False can be taken out--
        #--Need to figure out how to accept the StraboSpot SSL Certificate
        r = requests.post(url, json=data, headers=headers, verify= False)
        code = r.status_code
        QgsMessageLog.logMessage('Login Status Code: ' + str(code))
        # Check for a Bad Response- if so, warn the user and reset authorization vars
        if 400 <= code < 500:
            self.iface.messageBar().pushMessage("Error:", "Bad Response: check internet \
                                           connection or make sure to enter email AND \
                                           password.", QgsMessageBar.CRITICAL, 10)
            username = None
            password = None
            return
        # If not a Bad Response then check if the user's credentials are a valid account
        response = r.json()
        valid = response['valid']
        QgsMessageLog.logMessage(str(response) + valid)
        QgsMessageLog.logMessage('Response:' +  response["valid"])
        # Check the status code for success to move on
        if valid == 'true':
            #If the user is logged-in hide the log in widget and show choose one
            self.dlg.stackedWidget.setCurrentIndex(1)
        elif valid == 'false':
            self.iface.messageBar().pushMessage("Error:", "Login Failed. Try again.", QgsMessageBar.CRITICAL, 10)
            username = None
            password = None

    def deploydownloadGUI(self):
        # If the user wants to download a dataset, move to StraboChoose GUI
        self.dlg.stackedWidget.setCurrentIndex(2)

    def deployuploadGUI(self):
        #If the user wants to upload a dataset, move to uploadDatasets GUI
        self.dlg.stackedWidget.setCurrentIndex(4)

    def getprojects(self):
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
        #Add project names to projectlistWidget
        for prj in response['projects']:
            self.dlg.projectlistWidget.addItem(prj['name'])
            projectids.append(prj['id'])

    # Get the project id and then GET the datasets from that project
    # Dataset names are added to the datasetlistWidget
    def getprojectid(self):
        if self.dlg.datasetlistWidget.count() > 0:
            self.dlg.datasetlistWidget.clear()

        chosenid = self.dlg.projectlistWidget.currentRow()
        global projectname
        projectname = self.dlg.projectlistWidget.currentItem().text()
        QgsMessageLog.logMessage('Project Chosen :' + str(projectname) + ' Index of: ' + str(chosenid))
        projectid = projectids[chosenid]
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
        chosenid = self.dlg.datasetlistWidget.currentRow()
        global datasetname
        datasetname = self.dlg.datasetlistWidget.currentItem().text()
        QgsMessageLog.logMessage('Dataset Chosen :' + str(datasetname) + ' Index of: ' + str(chosenid))
        global datasetid
        datasetid = datasetids[chosenid]
        QgsMessageLog.logMessage('DatasetID: ' + str(datasetid))

    def downloadOptionsGUI(self):
        # Operates the 'Next' Button on the select project/dataset to download GUI
        self.dlg.stackedWidget.setCurrentIndex(3)

    def filebrowse(self):
        self.dlg.dialogPathlineEdit.setText(QFileDialog.getExistingDirectory(None, "Make a new folder here", os.path.expanduser("~"), QFileDialog.ShowDirsOnly))

    def importSpots(self):
        """Does most of the work in download process (**==NEEDS WORK)
        **NEEDS TO BE WRITTEN FOR EACH DATASET THAT GETS CHOSEN ONCE IT WORKS FOR ONE...
        1.) **GETs and Saves the GeoJSON for the spots - DONE
        2.) **GETs the images for the dataset if either of the two radio buttons are checked
        3.) **Puts the GeoJSON into QGIS-- Need to solve the problem with nested arrays
        4.) **Adds the GeoJSON layers in QGIS to some sort of database? SpatiaLite or PostGIS??"""
        directory = self.dlg.dialogPathlineEdit.text()
        # GET the datasetspots information from StraboSpot
        url = 'https://strabospot.org/db/datasetspotsarc/' + str(datasetid)
        QgsMessageLog.logMessage(url)
        r = requests.get(url, auth=HTTPBasicAuth(username, password), verify=False )
        statuscode = r.status_code
        response = r.json()
        projectfolder = projectname + datetime.datetime.now().strftime("_%m-%d-%y")
        directory = str.replace(str(directory), "\\", "/")
        datafolder = (str(directory) + '/' + projectfolder)
        QgsMessageLog.logMessage(str(directory))
        QgsMessageLog.logMessage(str(datafolder))
        if str(statuscode) == "200":  #If dataset is successfully transferred from StraboSpot
            if projectfolder in directory:
                datafolder = directory
            else:
                try:
                    os.makedirs(datafolder)
                except OSError as exception:
                    if exception.errno != errno.EEXIST:
                        raise
                    elif exception.errno == errno.EEXIST: #If the folder does exist
                        # Open file dialog again, prompting the user to make a more specific name
                        self.dlg.dialogPathlineEdit.setText(QFileDialog.getExistingDirectory(None, "Create a new folder.", directory, QFileDialog.ShowDirsOnly))
                        datafolder = self.dlg.dialogPathlineEdit.text()
                        #QFileDialog.getExistingDirectory(self, "Make a new folder here", directory, QFileDialog.ShowDirsOnly)
            QgsMessageLog.logMessage("Folder name: " + str(datafolder))

            # ADD LATER-- FOR EACH DATASET CHOSEN CREATE A "DATASET" FOLDER AND DO THE FOLLOWING
            # Save the datasetspots response to datafolder
            # This whole version of the dataset will be called upon during Upload
            rawjsonfile = datafolder + "\\" + datasetname + "_" + str(datasetid) + ".json"
            QgsMessageLog.logMessage('JSON file: ' + str(rawjsonfile))
            with open(rawjsonfile, 'w') as savedrawjson:
                json.dump(response, savedrawjson)

            """Begin Processing the Dataset for use in QGIS: 
            1.) Check dataset for images. If the dataset contains images AND one of the checkboxes
            (.jpeg or .tiff) are checked download the images to the datafolder.
            2.) Parse the raw GeoJSON to make new feature objects out of the nested arrays 
            (i.e. Orientation Data, Samples, Images, etc.) 
            3.) Get the edited JSON file into QGIS using New Vector Layer. 
            4.) Make a SpatiaLite database and save each layer file within the database.
            5.) (Optional) Save into a PostGIS database????"""

            geometryList = ['point', 'line', 'polygon']
            for geotype in geometryList:
                url = 'https://strabospot.org/db/datasetspotsarc/' + str(datasetid) + '/' + geotype
                r = requests.get(url, auth=HTTPBasicAuth(username, password), verify=False)
                statuscode = r.status_code
                response = r.json()
                if str(statuscode) == "200":  # If dataset is successfully transferred from StraboSpot

                        if str(response)== 'None': # If dataset doesn't have that geometry keep checking
                          continue

                        parsed = response
                        # Set Up and Advance to the Download Progress Widget
                        self.dlg.datasetNamelabel.setText("Dataset: " + datasetname + "...") #Need to work on resizing and centering
                        fullDataset = parsed['features']
                        imageCount = 0
                        for spot in fullDataset:
                            spotprop = spot['properties']
                            if 'images' in spotprop:
                                imgJson = spotprop['images']
                                for img in imgJson:
                                    imageCount +=1
                        QgsMessageLog.logMessage('Images in dataset: ' + str(imageCount))
                        self.dlg.downloadProgresslabel.setText("Downloading StraboSpot Project: " + projectname)    #Need to work on resizing
                        self.dlg.downloadprogressBar.setTextVisible(True)
                        self.dlg.downloadprogressBar.setMinimum(0)
                        self.dlg.downloadprogressBar.setValue(0)
                        downloadedimagescount = 0
                        if requestImages is True:
                            self.dlg.progBarLabel.setText("Preparing to download " + datasetname + " and " + str(imageCount) + " images.") #Need to work on resizing
                            progBarMax = imageCount + 3  # each downloaded image + (parsing GeoJSON, create layer, save layer(s) to db)
                            self.dlg.downloadprogressBar.setMaximum(progBarMax)
                            self.dlg.imageprogLabel.setText(
                                "Image " + str(downloadedimagescount) + " of " + str(imageCount) + " downloaded.")
                            imgFolder = str(datafolder) + "/" + datasetname + "_Images"
                            try:
                                os.makedirs(imgFolder)
                            except OSError as exception:
                                if exception.errno != errno.EEXIST:
                                    raise
                                elif exception.errno == errno.EEXIST:  # If the folder does exist then store in project folder
                                    imgFolder = datafolder
                        else:
                            progBarMax = 3 #parsing GeoJSON, create layer, save layer(s) to db (Perhaps this should be Spot#?)
                            self.dlg.downloadprogressBar.setMaximum(progBarMax)
                            self.dlg.progBarLabel.setText("Downloading StraboSpot dataset: " + datasetname + "...")

                        self.dlg.stackedWidget.setCurrentIndex(4)

                        # Iterate Spots to reorganize nested arrays and download images
                        newDatasetJson = []
                        for spot in fullDataset:
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
                            newSpot['properties'] = {'id': spotID, 'modified_timestamp' : spotModTS,
                                                   'time' : spottime, 'date' : spotdate, 'self' : spotself}
                            newDatasetJson.append(newSpot)
                            if 'orientation_data' in spotprop:
                                #Handle orientation data
                                ori_dataJson = spotprop['orientation_data']
                                for ori_data in ori_dataJson:   #Each set of measurements in the Orientation Data array
                                    newOri = {}
                                    newOri['type'] = 'Feature'
                                    newOri['geometry'] = spotgeometry
                                    newOri['properties'] = {}
                                    for key in ori_data:
                                        newOri['properties'][key] = ori_data.get(key)
                                    newOri['properties']['SpotID'] = spotID
                                    newDatasetJson.append(newOri)
                            if 'rock_unit' in spotprop:
                                #Handle rock unit data
                                rock_unitJson = spotprop['rock_unit']
                                newRockUnit = {}
                                newRockUnit['type'] = 'Feature'
                                newRockUnit['geometry'] = spotgeometry
                                newRockUnit['properties'] = {}
                                for key in rock_unitJson:
                                    newRockUnit['properties'][key] = rock_unitJson.get(key)
                                newRockUnit['properties']['SpotID'] = spotID
                                newDatasetJson.append(newRockUnit)
                            if 'trace' in spotprop:
                                # Handle trace data
                                traceJson= spotprop['trace']
                                newTrace = {}
                                newTrace['type'] = 'Feature'
                                newTrace['geometry'] = spotgeometry
                                newTrace['properties'] = {}
                                for key in traceJson:
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
                                        new3d['properties'][key] = _3DJson.get(key)
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
                                        newImg['properties'][key ] = img.get(key)
                                    newImg['properties']['SpotID'] = spotID
                                    newDatasetJson.append(newImg)
                                    # Save the actual image to disk
                                    imgURL = img.get('self')
                                    imgID = img.get('id')
                                    #QgsMessageLog.logMessage(imgURL)
                                    if requestImages is True:
                                        r = requests.get(imgURL, auth=HTTPBasicAuth(username, password), verify=False, stream=True)
                                        statuscode = r.status_code
                                        QgsMessageLog.logMessage(imgURL + " accessed with status code " + str(statuscode))
                                        if str(statuscode) == '200' :
                                            downloadedimagescount += 1
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

                        #Convert to GeoJson Array
                        fullJson = {'type': 'FeatureCollection',
                                      'features': newDatasetJson}
                        modifiedJson = json.dumps(fullJson)
                        modifiedJsonDict = json.loads(modifiedJson)
                        self.dlg.downloadprogressBar.setValue(downloadedimagescount + 1)
                        self.dlg.progBarLabel.setText("Creating QGIS layer of name: " + datasetname + "...")

                        #Save newly organized GeoJson array to file
                        modifiedFileName = datafolder + "\\" + datasetname + "_" + geotype + ".geojson"
                        modifiedFileName = str.replace(str(modifiedFileName), "\\", "/")
                        QgsMessageLog.logMessage('Modifided Json file: ' + modifiedFileName)
                        with open(modifiedFileName, 'w') as savemodJson:
                            json.dump(modifiedJsonDict, savemodJson)

                        #Add the modified Json file as a QGIS Layer
                        layername = datasetname + "_" + geotype
                        newlayer = QgsVectorLayer(modifiedFileName, layername, "ogr")
                        if not newlayer.isValid():
                            QgsMessageLog.logMessage("Layer is not valid...")
                        else:
                            QgsMapLayerRegistry.instance().addMapLayer(newlayer)
                        '''subLayers = newLayer.dataProvider().subLayers()
                        for sublayer in subLayers:
                            QgsMessageLog.logMessage(str(sublayer))
                            geometry = sublayer.split(':')[-1]
                            QgsMessageLog.logMessage(geometry)
                            newlayername = datasetname + "_" + geometry
                            #uri = "%s|layername=entities|geometrytype=%s" % (str(sublayer), geometry,)
                            subtoadd = QgsVectorLayer(sublayer, newlayername, 'ogr')
                            if not subtoadd.isValid():
                                QgsMessageLog.logMessage("Layer is not valid...")
                            else:
                                QgsMapLayerRegistry.instance().addMapLayer(subtoadd)'''

                        self.dlg.downloadprogressBar.setValue(downloadedimagescount + 2)
                        self.dlg.progBarLabel.setText("Saving QGIS layer to database...")

                        if self.dlg.downloadprogressBar.value == self.dlg.downloadprogressBar.maximum:
                            self.dlg.close()
        else:
            errorMsg = "Dataset, " + datasetname + ", could not be downloaded from StraboSpot."
            result = QMessageBox.critical(None, "Critical Error", errorMsg, QMessageBox.Ok)

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
                longitude= str(coordinates[0])
                latitude = str(coordinates[1])
            # Can only store one lat/long pair to Exif, so pull the first set of coordinates
            if geoType == "line":
                longitude = str(coordinates[0][0])
                latitude = str(coordinates[0][1])
            if geoType == "polygon":
                longitude = str(coordinates[0][0][0])
                latitude = str(coordinates[0][0][1])

            # Set Long/Lat Exif Refs
            if float(longitude) < 0:
                exif_dict['GPS'][piexif.GPSIFD.GPSLongitudeRef] = "W"
            else:
                exif_dict['GPS'][piexif.GPSIFD.GPSLongitudeRef] = "E"
            if float(latitude) < 0:
                exif_dict['GPS'][piexif.GPSIFD.GPSLatitudeRef] = "S"
            else:
                exif_dict['GPS'][piexif.GPSIFD.GPSLatitudeRef] = "N"

            # Convert from decimal degrees to degrees, minutes, seconds
            # Longitude
            abs_long = numpy.abs(float(longitude))
            long_mins, long_sec = divmod(abs_long*3600, 60)
            long_deg, long_mins = divmod(long_mins, 60)
            QgsMessageLog.logMessage("Long DMS: " + str(int(long_deg))+ "," + str(int(long_mins)) + "," + str(long_sec))
            # Latitude
            abs_lat = numpy.abs(float(latitude))
            lat_mins, lat_sec = divmod(abs_lat*3600, 60)
            lat_deg, lat_mins = divmod(lat_mins, 60)
            QgsMessageLog.logMessage("Lat DMS: " + str(int(lat_deg)) + "," + str(int(lat_mins)) + "," + str(lat_sec))
            #Save info to Exif
            exif_dict['GPS'][piexif.GPSIFD.GPSLongitude] = [(int(long_deg),1), (int(long_mins),1), (long_sec,10000000)]
            exif_dict['GPS'][piexif.GPSIFD.GPSLatitude] = [(int(lat_deg),1), (int(lat_mins),1), (lat_sec,10000000)]
            # Save edited Exif to Image
            exif_bytes = piexif.dump(exif_dict)
            savedImg.save(imageName, "jpeg", exif=exif_bytes)
        else:
            warningMsg = "Image file: \n" + imageName + "\n could not be geotagged. Click 'Ok' to continue downloading."
            result = QMessageBox.warning(None, "Error", warningMsg, QMessageBox.Ok)

    def run(self):
        """Run method that performs all the real work"""
        # show the dialog
        self.dlg.show()




