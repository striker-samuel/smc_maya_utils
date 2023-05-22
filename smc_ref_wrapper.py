
# Created by samuel.martin199@outlook.com at 22/05/2023


import os
import re
import json
import logging

import maya.cmds

class RefWrapper():

    def __init__(self, reference_node):

        self._reference_node = reference_node
        self._dirty_ns = False
        self._file = ""

        try:
            namespace = maya.cmds.getAttr("%s.cached_namespace" % self._reference_node)
        except ValueError:

            maya.cmds.lockNode(self._reference_node, l=False)
            maya.cmds.addAttr(self._reference_node, longName="cached_namespace", dataType="string")
            namespace = self.update_ns()
            maya.cmds.setAttr(self._reference_node + ".cached_namespace", namespace, type="string")
            maya.cmds.lockNode(self._reference_node, l=True)

        self._mats_file = ""
        self._mats_json = ""
        self._mat_data_list = ""

        self._cached_ns = namespace

    @property
    def reference_node(self):
        return self._reference_node

    @property
    def namespace(self):

        if self._dirty_ns:
            self.update_ns()

        return self._cached_ns

    @property
    def file(self):
        try:
            self._file = maya.cmds.referenceQuery(self.reference_node, filename=True, un=True)
        except RuntimeError:
            print("BE CAREFUL THIS REF HAS NO FILE ASSOCIATED %s" % self.reference_node)

            try:
                maya.cmds.lockNode(self.reference_node, l=False)
                maya.cmds.delete(self.reference_node)
            except Exception:
                pass

        return self._file

    @property
    def version(self):

        version_match = re.search("v(\d{3})",
                                  self.file,
                                  flags=re.IGNORECASE)

        if version_match:
            version = int(version_match.groups(1)[0])
        else:
            return 0

        return version

    def update_ns(self):

        maya.cmds.lockNode(self._reference_node, l=False)

        if maya.cmds.referenceQuery(self.reference_node, il=True):
            namespace = ":".join(maya.cmds.referenceQuery(self._reference_node, nodes=True)[0].split(":")[:-1])
        else:
            logging.info("TEMPORARY LOADING REF %s" % self.reference_node)
            maya.cmds.file(lr=self.reference_node)
            namespace = ":".join(maya.cmds.referenceQuery(self._reference_node, nodes=True)[0].split(":")[:-1])
            maya.cmds.file(unloadReference=self.reference_node)

        maya.cmds.lockNode(self._reference_node, l=True)
        self._cached_ns = namespace
        self._dirty_ns = False
        return namespace

    def new_namespace(self, new_namespace=""):

        if not new_namespace:
            new_namespace = os.path.basename(self.file).split(".")[0]

        if new_namespace == self.namespace:
            return

        if not maya.cmds.referenceQuery(self.reference_node, il=True):
            maya.cmds.file(self.file, lr=True)

        maya.cmds.file(self.file, r=True, sns=(self.namespace, new_namespace))
        maya.cmds.file(self.file, lr=True)

    @property
    def cache_folder(self):
        scene = maya.cmds.file(q=True, sn=True)

        shot_folder = os.path.dirname(
            os.path.dirname(scene)
        )

        return os.path.join(shot_folder, "cache")

    def export_cache(self):

        PREROLL_BUFFER_AMOUNT = 5

        if self.file.endswith(".abc"):
            return

        if not self.file:
            return

        if "/sets/" in self.file.replace("\\", "/"):
            return

        self.update_ns()

        export_path = os.path.join(self.cache_folder, "%s.geo.abc" % self.namespace)
        try:
            rfn = maya.cmds.referenceQuery(export_path, rfn=True)
            maya.cmds.file(unloadReference=rfn)
        except Exception as e:
            print(e)

        start_frame = 101
        end_frame = maya.cmds.playbackOptions(q=True, aet=True)

        start = start_frame - PREROLL_BUFFER_AMOUNT
        end = end_frame + PREROLL_BUFFER_AMOUNT

        rfn = maya.cmds.file(lr=self.reference_node)
        root = maya.cmds.referenceQuery(self.reference_node, nodes=True)[0]

        command = "-frameRange " + str(start) + " " + str(
            end) + " -uvWrite -writeVisibility -worldSpace -root " + root + " -file " + export_path

        maya.cmds.loadPlugin("AbcExport.mll")
        print(command)
        maya.cmds.AbcExport(j=command)

        self.export_mats()

        maya.cmds.namespace(set=":")

        return export_path

    def cache_reference(self):

        export_path = self.export_cache()

        try:
            cache_ref = maya.cmds.referenceQuery(export_path, rfn=True)
        except Exception:
            cache_ref = maya.cmds.file(export_path, r=True, ns=self.namespace + "_cache")

        # SMOOTH ABC
        nodes = maya.cmds.referenceQuery(cache_ref, nodes=True, dp=True)

        maya.cmds.select(nodes)
        maya.mel.eval(r"displaySmoothness -divisionsU 3 -divisionsV 3 -pointsWire 16 -pointsShaded 4 -polygonObject 3;")

        maya.cmds.namespace(set=":")
        if not "|__CACHES__" in maya.cmds.ls(assemblies=True, l=True):
            maya.cmds.group(name="|__CACHES__", em=True)
        if nodes:
            maya.cmds.parent(nodes[0], "|__CACHES__")

    def export_mats(self):

        if self.file.endswith(".abc"):
            return

        class mat_data:

            def __init__(self, matName, se, attr):
                self.name = matName
                self.shadingEngine_connected = se
                self.attrConnected_name = attr
                self.SE_faceList = []
                self.build()

            def build(self):

                SE_faceSet = maya.cmds.sets(self.shadingEngine_connected, q=True)
                self.SE_faceList = maya.cmds.ls(SE_faceSet)

            def toJSON(self):
                contentsDict = {}
                contentsDict['material'] = self.name
                contentsDict['SE_faceSets'] = self.SE_faceList
                contentsDict['SE_name'] = self.shadingEngine_connected
                contentsDict['SE_connectedAttr'] = self.attrConnected_name

                return contentsDict

        ref_nodes = maya.cmds.referenceQuery(self.reference_node, nodes=True)

        SE_list = [se for se in maya.cmds.ls(type='shadingEngine') if
                   se not in ['initialParticleSE', 'initialShadingGroup']]
        SE_list = [se for se in SE_list if se in ref_nodes]

        mat_data_list = []
        mats_to_export = []

        attrs = ['message', 'caching', 'frozen', 'isHistoricallyInteresting', 'nodeState', 'binMembership',
                 'hyperLayout',
                 'isCollapsed', 'blackBox', 'borderConnections', 'isHierarchicalConnection', 'publishedNodeInfo',
                 'publishedNodeInfo.publishedNode', 'publishedNodeInfo.isHierarchicalNode',
                 'publishedNodeInfo.publishedNodeType', 'rmbCommand', 'templateName', 'templatePath', 'viewName',
                 'iconName', 'viewMode', 'templateVersion', 'uiTreatment', 'customTreatment', 'creator', 'creationDate',
                 'containerType', 'dagSetMembers', 'dnSetMembers', 'memberWireframeColor', 'annotation', 'isLayer',
                 'verticesOnlySet', 'edgesOnlySet', 'facetsOnlySet', 'editPointsOnlySet', 'renderableOnlySet',
                 'partition',
                 'groupNodes', 'usedBy', 'hiddenInOutliner', 'unsolicited', 'displacementShader', 'imageShader',
                 'volumeShader', 'surfaceShader', 'defaultLights', 'linkedLights', 'ignoredLights', 'defaultShadows',
                 'dShadowDirection', 'dShadowDirectionX', 'dShadowDirectionY', 'dShadowDirectionZ', 'dShadowIntensity',
                 'dShadowIntensityR', 'dShadowIntensityG', 'dShadowIntensityB', 'dShadowAmbient', 'dShadowDiffuse',
                 'dShadowSpecular', 'dShadowShadowFraction', 'dShadowPreShadowIntensity', 'dShadowBlindData',
                 'linkedShadows', 'linkedShadows.lShadowDirection', 'linkedShadows.lShadowDirectionX',
                 'linkedShadows.lShadowDirectionY', 'linkedShadows.lShadowDirectionZ', 'linkedShadows.lShadowIntensity',
                 'linkedShadows.lShadowIntensityR', 'linkedShadows.lShadowIntensityG',
                 'linkedShadows.lShadowIntensityB',
                 'linkedShadows.lShadowAmbient', 'linkedShadows.lShadowDiffuse', 'linkedShadows.lShadowSpecular',
                 'linkedShadows.lShadowShadowFraction', 'linkedShadows.lShadowPreShadowIntensity',
                 'linkedShadows.lShadowBlindData', 'ignoredShadows', 'ignoredShadows.xShadowDirection',
                 'ignoredShadows.xShadowDirectionX', 'ignoredShadows.xShadowDirectionY',
                 'ignoredShadows.xShadowDirectionZ',
                 'ignoredShadows.xShadowIntensity', 'ignoredShadows.xShadowIntensityR',
                 'ignoredShadows.xShadowIntensityG',
                 'ignoredShadows.xShadowIntensityB', 'ignoredShadows.xShadowAmbient', 'ignoredShadows.xShadowDiffuse',
                 'ignoredShadows.xShadowSpecular', 'ignoredShadows.xShadowShadowFraction',
                 'ignoredShadows.xShadowPreShadowIntensity', 'ignoredShadows.xShadowBlindData', 'bogusAttribute',
                 'bogusAttribute.bogusDirection', 'bogusAttribute.bogusDirectionX', 'bogusAttribute.bogusDirectionY',
                 'bogusAttribute.bogusDirectionZ', 'bogusAttribute.bogusIntensity', 'bogusAttribute.bogusIntensityR',
                 'bogusAttribute.bogusIntensityG', 'bogusAttribute.bogusIntensityB', 'bogusAttribute.bogusAmbient',
                 'bogusAttribute.bogusDiffuse', 'bogusAttribute.bogusSpecular', 'bogusAttribute.bogusShadowFraction',
                 'bogusAttribute.bogusPreShadowIntensity', 'bogusAttribute.bogusBlindData', 'rsSurfaceShader',
                 'rsVolumeShader', 'rsShadowShader', 'rsPhotonShader', 'rsEnvironmentShader', 'rsBumpmapShader',
                 'rsDisplacementShader', 'rsMaterialId']
        attrs_to_check = [attr for attr in attrs if "Shader" in attr]

        for se in SE_list:

            for attr in attrs_to_check:

                try:
                    attr_mat = maya.cmds.listConnections(se + ".%s" % attr, d=False, s=True)[0]
                    mats_to_export.append(attr_mat)
                    mat_data_list.append(mat_data(attr_mat, se, '.%s' % attr))

                    print("%s USED IN " % attr.upper() + se)
                except Exception as e:
                    # print("NO %s USED IN " % attr.upper() + se)
                    pass

        # PATH CREATION

        mats_file_exportPath = os.path.join(self.cache_folder,
                                            self.namespace.replace("_cache", "") + "_mats.mb")

        mats_json_exportPath = os.path.join(self.cache_folder,
                                            self.namespace.replace("_cache", "") + "_matsSerialized.json")

        ##EXPORT MAYA FILE

        maya.cmds.select(mats_to_export)
        maya.cmds.select(SE_list, ne=True, add=True)

        for x in maya.cmds.ls(type="unknown"):
            maya.cmds.delete(x)

        maya.cmds.file(mats_file_exportPath, es=True, f=True, type='mayaBinary')
        maya.cmds.file(mats_file_exportPath.replace(".mb", ".ma"), es=True, f=True, type='mayaAscii')

        # EXPORT JSON
        with open(mats_json_exportPath, 'w') as outfile:
            json.dump({"materials": [mat.toJSON() for mat in mat_data_list]}, outfile, sort_keys=True, indent=4)

        self._mats_file = mats_file_exportPath
        self._mats_json = mats_json_exportPath
        self._mat_data_list = mat_data_list

        return mats_file_exportPath, mat_data_list

    def apply_mats(self):

        if not self.file.endswith(".abc"):
            return

        if not self.namespace:
            return

        maya.cmds.file(lr=self.reference_node)
        maya_file_import_path = os.path.join(self.cache_folder,
                                             self.namespace.replace("_cache", "") + "_mats.mb")

        json_se_file_import_path = os.path.join(self.cache_folder,
                                                self.namespace.replace("_cache", "") + "_matsSerialized.json")

        print(maya_file_import_path)
        print(json_se_file_import_path)

        if not os.path.exists(maya_file_import_path):
            return

        ns = "MATERIALS_%s" % self.namespace
        maya.cmds.file(maya_file_import_path, i=True, ns=ns)
        failures = []

        with open(json_se_file_import_path) as json_file:
            data = json.load(json_file)
            for material in data["materials"]:
                for selectable in material["SE_faceSets"]:
                    selectable_no_ns = re.sub("^[^:]*", "", selectable)

                    print(self.namespace)
                    print(selectable_no_ns)

                    try:
                        maya.cmds.select("%s%s" % (self.namespace, selectable_no_ns))

                        # CANT BE RUN IN MAYA INTERACTIVE
                        # maya.cmds.hyperShade(assign=ns + ":" + material["material"])
                        maya.cmds.sets(fe=ns + ":" + material["SE_name"], e=True)
                    except Exception as e:
                        failures.append(e)
                        print(e)

        for x in failures:
            print("FAILED :::::: %s" % str(x))
