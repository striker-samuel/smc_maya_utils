import os
import re
import tempfile

import maya.cmds as cmds

from PySide2 import QtCore
from PySide2 import QtGui
from PySide2.QtCore import Qt
import PySide2.QtWidgets as QtWidgets

import smc_ref_wrapper
import alert_dialog

__all__ = ["GpuCacherTool"]


def get_refs():
    refs = {}
    for rfn in cmds.ls(type="reference"):
        try:
            if cmds.referenceQuery(rfn, filename=True, un=True):
                refs[rfn] = cmds.referenceQuery(rfn, filename=True, un=True)
        except RuntimeError:
            continue

    return refs


def get_refs_in_scene_wrap():
    found = []
    for ref, file in get_refs().items():

        if "LAYOUTCACHE" in ref:
            continue

        if "cam_" in ref:
            continue

        w_ref = smc_ref_wrapper.RefWrapper(ref)
        found.append((w_ref.namespace, w_ref.version, w_ref.reference_node))

    return found


class GpuCacheWrapper():
    """
    Wrapper for gpu cahe_node. Character(rfn) driven
    """

    BUFFER_AMOUNT = 5

    def __init__(self, rfns, start, end, dir="", name=""):

        import tempfile

        if not dir:
            dir = tempfile.gettempdir()

        self.dir = dir
        self._rfns = rfns

        self._start = start
        self._end = end

        self._active = False
        self._exported = False
        self._filepath = ""

        start_name = os.path.basename(cmds.file(q=True, sn=True)).split(".")[0]

        self._cache_node = ""

        if "GPU_CACHES" not in cmds.ls(assemblies=True):
            cmds.createNode("transform", name="GPU_CACHES")

        if name == "":
            import random
            import string
            _random_string_shot = ''.join(random.choices(string.ascii_letters, k=6))
            name = _random_string_shot

        node_name = "gpuCache_" + name

        for cache_node in cmds.ls(type="gpuCache"):

            refs_list = []

            try:
                refs_list = cmds.getAttr("%s.refNodes" % cache_node)
                print(refs_list)
            except ValueError:
                continue

            if not refs_list:
                cmds.delete(cache_node)
                continue

            refs_list.sort()

            if refs_list == sorted(self._rfns):

                if not os.path.exists(cmds.getAttr(cache_node + ".storedPath")):
                    cmds.delete(cache_node)
                    continue

                self._cache_node = cache_node
                refs_no_ns = [re.sub("RN$", "", re.sub(".*:", "", ref)) for ref in self.rfns]
                self._filepath = os.path.join(self.dir,
                                              "%s_" % start_name + self.cache_node + "_%s_%i_%i_.abc" % (
                                                  "_".join(refs_no_ns), start, end))

                break

        if self.cache_node == "":
            self._cache_node = cmds.createNode("gpuCache", parent="GPU_CACHES", name=node_name)

            cmds.addAttr(self.cache_node, longName="refNodes", dataType="stringArray")

            # cmds.addAttr(self.cache_node, longName = "startFrame", attributeType = "float")
            # cmds.addAttr(self.cache_node, longName = "endFrame", attributeType = "float")
            # cmds.setAttr(self.cache_node + ".startFrame", float(start) ,type="float")
            # cmds.setAttr(self.cache_node + ".endFrame", float(end) ,type="float")

            # print(re.sub(":.*RN", "" , " ".join(self._rfns)))
            cmds.setAttr(self.cache_node + ".refNodes", *([len(self._rfns)] + self._rfns), type="stringArray")

            refs_no_ns = [re.sub("RN$", "", re.sub(".*:", "", ref)) for ref in self.rfns]
            self._filepath = os.path.join(self.dir, "%s_" % start_name + self.cache_node + "_%s_%i_%i_.abc" % (
                "_".join(refs_no_ns), start, end))

            cmds.addAttr(self.cache_node, longName="storedPath", dataType="string")
            cmds.setAttr(self.cache_node + ".storedPath", self.filepath, type="string")

    @property
    def cache_node(self):
        return self._cache_node

    @property
    def start(self):
        return self._start

    @property
    def end(self):
        return self._end

    @property
    def active(self):

        self._active = cmds.getAttr(self.cache_node + ".cacheFileName")
        return self._active

    @property
    def rfns(self):

        # print(re.sub(":.*RN", "", " ".join(self._rfns)))
        # cmds.setAttr(self.cache_node + ".refNodes",re.sub(":.*RN", "" , " ".join(self._rfns)), type="stringArray")
        return self._rfns

    @property
    def filepath(self):
        return self._filepath

    @property
    def exported(self):
        self._exported = os.path.exists(self.filepath)
        return self._exported

    def export_abc(self):
        """Exports cache to self.dir of self.rfns"""

        start_frame = cmds.playbackOptions(q=True, ast=True)
        end_frame = cmds.playbackOptions(q=True, aet=True)

        start = start_frame - self.BUFFER_AMOUNT
        end = end_frame + self.BUFFER_AMOUNT

        roots = []

        for rfn in self.rfns:

            if not cmds.referenceQuery(rfn, isLoaded=True):
                cmds.file(loadReference=rfn)

            print("Loaded REF %s" % rfn)
            roots.append(cmds.referenceQuery(rfn, nodes=True)[0])

        cache_roots = [roots[0]]

        try:
            os.remove(self.filepath)
        except Exception as e:
            print(e)

        command = "gpuCache -startTime {} -endTime {} -optimize -optimizationThreshold 40000 " \
                  "-writeMaterials -dataFormat ogawa -directory \"{}\" -fileName \"{}\" " \
                  "-saveMultipleFiles false ".format(start,
                                                     end,
                                                     os.path.dirname(self.filepath.replace('\\', '/')),
                                                     os.path.basename(self.filepath.replace(".abc", "")))

        command += " ".join(cache_roots) + ";"

        import maya.mel
        print("GPU CACHE EXPORT")
        print(command)
        maya.mel.eval(command)

    def turn_on_cache(self):

        for rfn in self.rfns:
            cmds.file(unloadReference=rfn)

        try:
            cmds.setAttr(self.cache_node + ".cacheFileName", "", type="string")
            cmds.setAttr(self.cache_node + ".cacheFileName", self.filepath, type="string")

            self._active = True

        except Exception as e:
            print(e)

    def turn_off_cache(self):

        for rfn in self.rfns:
            cmds.file(loadReference=rfn)

        try:
            cmds.setAttr(self.cache_node + ".cacheFileName", "", type="string")

            self._active = False

        except Exception as e:
            print(e)


class GpuCacherTool(QtWidgets.QWidget):
    BUFFER_AMOUNT = 5

    def __init__(self):
        super(GpuCacherTool, self).__init__()

        cmds.loadPlugin("gpuCache.mll")

        self.CACHES_DIR = ""

        self.caches = []
        self._ref_lock = True

        self.setWindowTitle("Gpu Cacher Tool")
        self.setWindowFlags(QtCore.Qt.WindowStaysOnTopHint)

        main_layout = QtWidgets.QVBoxLayout(self)

        self.local_path_led = QtWidgets.QLabel()
        os.makedirs(os.path.join(tempfile.gettempdir(), "a_gpuCacherTemp"), exist_ok=True)

        self.local_path_led.setText(os.path.join(tempfile.gettempdir(), "a_gpuCacherTemp"))

        horizontal_layout_wdg = QtWidgets.QWidget()
        horizontal_layout = QtWidgets.QHBoxLayout()
        horizontal_layout_wdg.setLayout(horizontal_layout)
        self.choose_dir_button = QtWidgets.QPushButton("Choose dir")
        self.choose_dir_button.released.connect(self.choose_dir)

        horizontal_layout.addWidget(self.choose_dir_button)
        horizontal_layout.addWidget(self.local_path_led)

        tables_area = QtWidgets.QWidget()
        tables_area_lyt = QtWidgets.QHBoxLayout(tables_area)
        tables_area_lyt.setContentsMargins(0, 0, 0, 0)

        horizontal_layout.setMargin(0)
        main_layout.addWidget(horizontal_layout_wdg)

        ##TABLE LEFT
        self.asset_table = QtWidgets.QTableWidget(0, 1)

        self.asset_table.verticalHeader().hide()
        self.asset_table.verticalHeader().setDefaultSectionSize(22)
        self.asset_table.horizontalHeader().setDefaultSectionSize(60)
        self.asset_table.setColumnWidth(5, 40)
        # self.asset_table.setSelectionBehavior(QtWidgets.QTableView.SelectRows)
        self.asset_table.setStyleSheet(
            """QTableWidget::item {padding-right: 5px; border: 0px};setColumnWidth(1, 40);""")

        self.asset_table.setSizeAdjustPolicy(QtWidgets.QAbstractScrollArea.AdjustToContents)
        self.asset_table.resizeColumnsToContents()

        self.table_header_names = ["Reference"]

        header = self.asset_table.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)

        self.asset_table.setSelectionMode(QtWidgets.QAbstractItemView.MultiSelection)
        self.asset_table.itemSelectionChanged.connect(self._selection_changed)

        ## TABLE_RIGHT
        self.cache_table = QtWidgets.QTableWidget(0, 2)

        self.cache_table.verticalHeader().hide()
        self.cache_table.verticalHeader().setDefaultSectionSize(22)
        self.cache_table.horizontalHeader().setDefaultSectionSize(60)
        self.cache_table.setColumnWidth(5, 40)
        self.cache_table.setSelectionBehavior(QtWidgets.QTableView.SelectRows)
        self.cache_table.setStyleSheet(
            """QTableWidget::item {padding-right: 5px; border: 0px};setColumnWidth(1, 40);""")
        self.cache_table.setSizeAdjustPolicy(QtWidgets.QAbstractScrollArea.AdjustToContents)
        self.cache_table.resizeColumnsToContents()

        self.cache_table_header_names = ["Gpu Cache", "State", "Re-Export", "Delete"]

        header = self.cache_table.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)

        self.cache_table.setHorizontalHeaderLabels(self.cache_table_header_names)
        self.cache_table.itemSelectionChanged.connect(self._cache_selection_changed)

        tables_area_lyt.addWidget(self.asset_table)
        tables_area_lyt.addWidget(self.cache_table)

        main_layout.addWidget(tables_area)

        do_cache_button = QtWidgets.QPushButton("Make GPU cache")
        do_cache_button.released.connect(self._do_cache)

        clear_temp_button = QtWidgets.QPushButton("Remove all caches from temp")
        clear_temp_button.released.connect(self._clear_temp)

        repair_button = QtWidgets.QPushButton("Repair nodes from folder")
        repair_button.released.connect(self._repair)

        delete_button = QtWidgets.QPushButton("Delete All GpuCahes")
        delete_button.released.connect(self._delete_all)

        main_layout.addWidget(do_cache_button)
        main_layout.addWidget(repair_button)
        main_layout.addWidget(delete_button)
        main_layout.addWidget(clear_temp_button)

        self._repair()

        self.show()

    ##UI

    def choose_dir(self):

        gpucache_path = QtWidgets.QFileDialog.getExistingDirectory(self, "Select Directory", tempfile.gettempdir())
        if gpucache_path != "":
            self.local_path_led.setText(gpucache_path)

    def _cache_selection_changed(self):

        print(self.cache_table.selectedItems())

        if not self.cache_table.selectedItems():
            cmds.select(clear=True)
            return

        items = []

        for selection in self.cache_table.selectedItems():

            refNodes = cmds.getAttr("%s.refNodes" % selection.data(1))
            for ref_node in refNodes:
                print(ref_node)
                [items.append(item) for item in
                 self.asset_table.findItems(re.sub(":.*$", "", ref_node), Qt.MatchContains)]

        for item in self.asset_table.selectedItems():
            item.setSelected(False)

        for item in items:
            item.setSelected(True)

    def _selection_changed(self, *args):

        if not self.asset_table.selectedItems():
            cmds.select(clear=True)
            return

        to_select = []

        for selection in self.asset_table.selectedItems():

            selected = selection.text()

            for namespace, version, ref in get_refs_in_scene_wrap():

                try:
                    if ref == "sharedReferenceNode":
                        continue

                    file = cmds.referenceQuery(ref, filename=True)
                    if file.endswith(".abc"):
                        continue

                    ns = cmds.referenceQuery(file, ns=True, shn=True)
                    if ns == selected:
                        to_select.append(cmds.referenceQuery(ref, nodes=True)[0])

                except Exception as e:
                    print(e)
                    pass

        cmds.select(to_select)

    def _refresh_tables(self):

        self.asset_table.clear()
        self.asset_table.setRowCount(0)
        self.asset_table.setColumnCount(len(self.table_header_names))

        self.cache_table.clear()
        self.cache_table.setRowCount(0)
        self.cache_table.setColumnCount(len(self.cache_table_header_names))

        self.fill_table()

    @property
    def info_dict(self):

        info_dict = {}

        for namespace, version, rfnnode in get_refs_in_scene_wrap():
            info_dict[namespace] = {"ref": rfnnode}

        return info_dict

    def fill_table(self):

        self.asset_table.setHorizontalHeaderLabels(self.table_header_names)
        self.asset_table.setSortingEnabled(0)

        i = 0
        for key, values in self.info_dict.items():

            font = QtGui.QFont()
            font.setBold(True)

            item = QtWidgets.QTableWidgetItem(key)
            item.setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled)
            item.setTextAlignment(QtCore.Qt.AlignCenter | QtCore.Qt.AlignVCenter)

            item.setText(key)

            try:
                self.asset_table.insertRow(i)
                self.asset_table.setItem(0, i, item)
                print(item.text())
                self.asset_table.item(0, i).setFont(
                    font)

                if self._is_ref_in_cache(values["ref"]):
                    item.setForeground(Qt.blue)

                i += 1

            except KeyError:
                continue

            except Exception as e:
                print(e)
                continue

        self.cache_table.setHorizontalHeaderLabels(self.cache_table_header_names)
        self.cache_table.setSortingEnabled(0)

        for j, cache in enumerate(self._ls_gpuCaches()):

            self.cache_table.insertRow(j)

            font = QtGui.QFont()
            font.setBold(True)

            _item = QtWidgets.QTableWidgetItem(str(cache))
            _item.setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled)
            _item.setTextAlignment(QtCore.Qt.AlignCenter | QtCore.Qt.AlignVCenter)

            _item.setData(1, cache)

            _item.setText(re.sub("_\w{6}$", "", cache) + ": %s" % ", ".join(
                [re.sub(":.*", "", ref) for ref in (cmds.getAttr(cache + ".refNodes"))]))

            # _item.setText(cache)

            self.cache_table.setItem(j, 0, _item)

            switch_button = QtWidgets.QPushButton()
            switch_button.setStyleSheet(
                "background-color:green"
            )

            switch_button.setCheckable(True)
            switch_button.setProperty("cache_node", cache)
            switch_button.released.connect(self._switched)

            switch_button.setChecked(not self._query_cache_status(cache))
            self.cache_table.setCellWidget(j, 1, switch_button)

            re_export_button = QtWidgets.QPushButton("Re-Export")
            re_export_button.setProperty("cache_node", cache)
            re_export_button.released.connect(self._re_export)

            self.cache_table.setCellWidget(j, 2, re_export_button)

            delete_and_load_button = QtWidgets.QPushButton("Del")
            delete_and_load_button.setProperty("cache_node", cache)
            delete_and_load_button.released.connect(self._delete_and_load)

            self.cache_table.setCellWidget(j, 3, delete_and_load_button)

            if self.cache_table.item(j, 0):
                self.cache_table.item(j, 0).setFont(font)

        self.asset_table.sortItems(0, QtCore.Qt.AscendingOrder)
        self.asset_table.setSortingEnabled(0)

        # LOCK SELECTION
        for i in range(self.asset_table.rowCount()):
            for j in range(self.asset_table.columnCount()):
                item = self.asset_table.item(i, j)
                if not item:
                    _item = QtWidgets.QTableWidgetItem()
                    self.asset_table.setItem(i, j, _item)
                    _item.setFlags(_item.flags() & Qt.ItemIsSelectable)

        self.cache_table.setSortingEnabled(1)

    def _switched(self, *args):

        cache_name = self.sender().property("cache_node")
        if not self._query_cache_status(cache_name):
            cmds.setAttr(cache_name + ".cacheFileName", cmds.getAttr(cache_name + ".storedPath"), type="string")
        else:
            cmds.setAttr(cache_name + ".cacheFileName", "", type="string")

    def _re_export(self):
        """
        Re-Exports selected cache with current playback range
        """

        cache_node = self.sender().property("cache_node")
        rfns = cmds.getAttr(cache_node + ".refNodes")
        re_cache = GpuCacheWrapper(rfns, cmds.playbackOptions(q=True, ast=True),
                                   cmds.playbackOptions(q=True, aet=True),
                                   dir=self.local_path_led.text())

        re_cache.export_abc()
        re_cache.turn_on_cache()

    def _delete_all(self):

        for cache in cmds.listRelatives("GPU_CACHES", type="gpuCache"):

            for ref in cmds.getAttr(cache + ".refNodes"):
                cmds.file(lr=ref)

            cmds.delete(cache)

        for file in os.listdir(self.local_path_led.text()):
            if os.path.basename(cmds.file(q=True, sn=True)).split(".")[0] in file:
                os.remove(os.path.join(self.local_path_led.text(), file))

        cmds.delete("GPU_CACHES")

        self._refresh_tables()

    def _delete_and_load(self):

        cache_node = self.sender().property("cache_node")

        for cache in [cache_node]:

            os.remove(cmds.getAttr("%s.storedPath" % cache))

            for ref in cmds.getAttr(cache + ".refNodes"):
                cmds.file(lr=ref)

            cmds.delete(cache)

        # for file in os.listdir(self.local_path_led.text()):
        #     if os.path.basename(cmds.file(q=True, sn=True)).split(".")[0] in file:
        #         os.remove(os.path.join(self.local_path_led.text(), file))

        # cmds.delete("GPU_CACHES")

        self._refresh_tables()

    def _repair(self):

        for file in os.listdir(self.local_path_led.text()):
            print("FILE %s" % file)

            if os.path.basename(cmds.file(q=True, sn=True)).split(".")[0] not in file:
                continue

            file_no_scene_name = re.sub(os.path.basename(cmds.file(q=True, sn=True)).split(".")[0] + "_", "", file)
            # print(file_no_scene_name)

            name_match = re.match("gpuCache_([^_]*)", file_no_scene_name)
            # gpuCache_aMXTaW_chr_bony_1096_1182_.abc
            ext = re.sub("gpu_cache_\w{6}_", "", file)
            if name_match:
                name = name_match.group(1)

            valid_prefixes = ["chr", "spr", "prp", "set"]

            # results = re.findall("|".join(valid_prefixes) + "_[^_]*", ext, flags=re.IGNORECASE)
            results = re.findall("(?:chr|spr|prp|set)_[^_]*", ext, flags=re.IGNORECASE)
            # ""

            refs = []

            for result in results:
                print(result)

                for ref in cmds.ls(type="reference"):
                    if "LAYOUTCACHE" in ref:
                        continue

                    try:
                        unique_ns = cmds.referenceQuery(ref, ns=True, shn=True)

                    except Exception as e:
                        print(e)
                        print(ref)
                        unique_ns = re.sub("RN$", "", ref)
                        unique_ns = re.sub("^[^:]*:", "", unique_ns)
                        print(unique_ns)

                    if unique_ns == result:
                        refs.append(ref)
                        continue

            # print(refs)
            if not refs:
                print("|".join(valid_prefixes) + "_[^_]*")
                print("ABC FILE %s REFS NOT IN SCENE!" % file)
                # cmds.error()
                return

            repaired_cache = GpuCacheWrapper(refs, cmds.playbackOptions(q=True, ast=True),
                                             cmds.playbackOptions(q=True, aet=True),
                                             self.local_path_led.text(),
                                             name=name)

            repaired_cache._exported = True
            print("FILEPATH %s" % repaired_cache.filepath)
            # repaired_cache.turn_on_cache()

        self._refresh_tables()

    def _clear_temp(self):

        import os
        for file in os.listdir(tempfile.gettempdir()):
            if os.path.basename(file).endswith(".abc"):
                if file.startswith("gpuCahe_"):
                    try:
                        os.remove(file)
                        print("REMOVED %s" % file)
                    except Exception as e:
                        print(e)

    def _do_cache(self):

        if not self.asset_table.selectedItems():
            cmds.select(clear=True)
            return

        selected_unique_names = [selected.text() for selected in self.asset_table.selectedItems()]

        start = cmds.playbackOptions(q=True, ast=True)
        end = cmds.playbackOptions(q=True, aet=True)
        selected_refs = ([self.info_dict[str(selected)]["ref"] for selected in selected_unique_names])

        if self._ref_lock:
            for ref in selected_refs:
                cache = self._is_ref_in_cache(ref)
                if cache:
                    alert_dialog.AlertDialog(
                        "Ref %s is already used in cache: %s \n Delete the gpuCache containing it" % (
                            ref, cache + ": %s" % ", ".join(
                                [re.sub(":.*", "", ref) for ref in (cmds.getAttr(cache + ".refNodes"))])))
                    return

        dir = self.local_path_led.text()
        new_cache = GpuCacheWrapper(selected_refs, start, end, dir=dir)

        if not new_cache.exported:
            new_cache.export_abc()

        new_cache.turn_on_cache()

        self._refresh_tables()

    def _is_ref_in_cache(self, ref):

        for cache in self._ls_gpuCaches():
            if ref in cmds.getAttr("%s.refNodes" % cache):
                return cache

        return False

    def _query_cache_status(self, cache_name):

        if cmds.getAttr(cache_name + ".cacheFileName"):
            return True
        else:
            return False

    def _ls_gpuCaches(self, asset=""):

        caches = []

        for cache in cmds.ls(type="gpuCache"):
            print(cache)

            try:
                for ref in cmds.getAttr("%s.refNodes" % cache):
                    print("Asset %s" % asset)
                    if not asset:
                        if cache not in caches:
                            caches.append(cache)
                            continue

                    if asset in ref:
                        # if cmds.getAttr("%s.cacheFileName" % cache) !=
                        if cache not in caches:
                            caches.append(cache)

            except ValueError as e:
                # print(e)
                pass
            except TypeError as e:
                # print(e)
                pass

        print(caches)

        return caches


if __name__ == "__main__":
    gpu_cacher = GpuCacherTool()
