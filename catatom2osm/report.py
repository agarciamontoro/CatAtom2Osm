"""Statistics report."""
import io
import json
import locale
import platform
import time
from collections import Counter, OrderedDict
from datetime import datetime

import psutil

from catatom2osm import config

TAB = "  "
SEP = ": "
MEMORY_UNIT = 1048576.0
MEMORY_LABEL = "MB"
int_format = lambda v: locale.format_string("%d", v, True)


class Report(object):
    def __init__(self, **kwargs):
        self.titles = OrderedDict(
            [
                ("fixme_counter", None),
                ("min_level", None),
                ("max_level", None),
                ("building_counter", None),
                ("mun_name", _("Municipality")),
                ("cat_mun", _("Cadastre name")),
                ("mun_code", _("Code")),
                ("date", _("Date")),
                ("options", _("Options")),
                ("group_system_info", _("System info")),
                ("app_version", _("Application version")),
                ("platform", _("Platform")),
                ("language", _("Language")),
                ("qgs_version", _("QGIS version")),
                ("gdal_version", _("GDAL version")),
                ("cpu_count", _("CPU count")),
                ("cpu_freq", _("CPU frequency")),
                ("ex_time", _("Execution time")),
                ("memory", _("Total memory")),
                ("rss", _("Physical memory usage")),
                ("vms", _("Virtual memory usage")),
                ("group_address", _("Addresses")),
                ("subgroup_ad_cdau", "CDAU"),
                ("inp_address_cdau", _("Feature count")),
                ("rep_address_cdau", _("Replaced addresses")),
                ("add_address_cdau", _("Added addresses")),
                ("subgroup_ad_input", _("Input data")),
                ("address_date", _("Source date")),
                ("inp_address", _("Feature count")),
                ("inp_address_entrance", TAB + _("Type entrance")),
                ("inp_address_parcel", TAB + _("Type parcel")),
                ("inp_zip_codes", _("Postal codes")),
                ("inp_street_names", _("Street names")),
                ("subgroup_ad_process", _("Process")),
                (
                    "orphaned_addresses",
                    _("Addresses without associated building excluded"),
                ),
                ("ignored_addresses", _("Addresses deleted by street name")),
                (
                    "addresses_without_number",
                    _("Addresses without house number deleted"),
                ),
                (
                    "multiple_addresses",
                    _("Addresses belonging to multiple buildings deleted"),
                ),
                (
                    "not_unique_addresses",
                    _("'Parcel' addresses not unique for its building deleted"),
                ),
                ("subgroup_ad_conflation", _("Conflation")),
                ("osm_addresses", _("OSM addresses ")),
                ("osm_addresses_without_number", TAB + _("Without house number")),
                (
                    "refused_addresses",
                    _("Addresses rejected because they exist in OSM"),
                ),
                ("subgroup_ad_output", _("Output data")),
                ("out_address", _("Addresses")),
                ("out_address_entrance", TAB + _("In entrance nodes")),
                ("out_address_parcel", TAB + _("In parcels")),
                ("out_addr_str", TAB + _("Type addr:street")),
                ("out_addr_plc", TAB + _("Type addr:place")),
                ("group_buildings", _("Buildings")),
                ("subgroup_bu_input", _("Input data")),
                ("building_date", _("Source date")),
                ("inp_features", _("Feature count")),
                ("inp_buildings", TAB + _("Buildings")),
                ("inp_parts", TAB + _("Building parts")),
                ("inp_pools", TAB + _("Swimming pools")),
                ("orphaned_parts", _("Parts without associated building excluded")),
                ("subgroup_bu_process", _("Process")),
                ("parts_wo_building", _("Parts without building deleted")),
                ("outside_parts", _("Parts outside outline deleted")),
                ("underground_parts", _("Parts with no floors above ground")),
                ("multipart_geoms_building", _("Buildings with multipart geometries")),
                (
                    "exploded_parts_building",
                    _("Buildings resulting from splitting multiparts"),
                ),
                ("parts_to_outline", _("Parts merged to the outline")),
                ("adjacent_parts", _("Adjacent parts merged")),
                (
                    "buildings_in_pools",
                    _("Buildings coincidents with a swimming pool deleted"),
                ),
                ("geom_parts_building", _("Invalid geometry parts deleted")),
                ("geom_rings_building", _("Invalid geometry rings deleted")),
                ("geom_invalid_building", _("Invalid geometries deleted")),
                ("vertex_zigzag_building", _("Zig-zag vertices deleted")),
                ("vertex_spike_building", _("Spike vertices deleted")),
                ("vertex_close_building", _("Close vertices merged")),
                ("vertex_topo_building", _("Topological points created")),
                ("vertex_simplify_building", _("Simplified vertices")),
                ("subgroup_bu_conflation", _("Conflation")),
                ("osm_buildings", _("Buildings/pools in OSM")),
                ("osm_building_conflicts", TAB + _("With conflict")),
                ("subgroup_bu_output", _("Output data")),
                ("nodes", _("Nodes")),
                ("ways", _("Ways")),
                ("relations", _("Relations")),
                ("out_features", _("Feature count")),
                ("out_buildings", TAB + _("Buildings")),
                ("out_parts", TAB + _("Buildings parts")),
                ("out_pools", TAB + _("Swimming pools")),
                ("pools_on_roofs", TAB + TAB + _("Over buildings")),
                ("building_types", _("Building types counter")),
                ("dlag", _("Max. levels above ground (level: # of buildings)")),
                ("dlbg", _("Min. levels below ground (level: # of buildings)")),
                ("group_tasks", _("Project")),
                ("tasks", _("Tasks files")),
                ("tasks_r", TAB + _("Rustic")),
                ("tasks_u", TAB + _("Urban")),
                ("group_problems", _("Problems")),
                ("errors", _("Report validation:")),
                ("fixme_count", _("Fixmes")),
                ("fixmes", ""),
                ("warnings", _("Warnings:")),
            ]
        )
        self.formats = {
            "cpu_freq": lambda v: locale.format_string("%.1f Mhz", v, True),
            "ex_time": lambda v: locale.format_string("%.1f " + _("seconds"), v, True),
            "memory": lambda v: locale.format_string("%.2f ", v, True) + MEMORY_LABEL,
            "rss": lambda v: locale.format_string("%.2f ", v, True) + MEMORY_LABEL,
            "vms": lambda v: locale.format_string("%.2f ", v, True) + MEMORY_LABEL,
        }
        self.clear(**kwargs)

    def clear(self, **kwargs):
        self.start_time = time.time()
        self.values = {
            "date": datetime.now().strftime("%x"),
            "warnings": [],
            "errors": [],
            "min_level": {},
            "max_level": {},
            "fixme_counter": Counter(),
            "building_counter": Counter(),
        }
        self.get_sys_info()
        self.tasks_with_fixmes = set()
        for k, v in list(kwargs.items()):
            self.values[k] = v

    def __setattr__(self, key, value):
        if key != "titles" and key in self.titles.keys():
            self.values[key] = value
        else:
            super(Report, self).__setattr__(key, value)

    def __getattr__(self, key):
        if key != "titles" and key in self.titles.keys():
            return self.values[key]
        else:
            return super(Report, self).__getattribute__(key)

    def address_stats(self, address_osm):
        for el in address_osm.elements:
            if "addr:street" in el.tags:
                self.inc("out_addr_str")
            if "addr:place" in el.tags:
                self.inc("out_addr_plc")
            if "addr:street" in el.tags or "addr:place" in el.tags:
                self.inc("out_address")
                if el.type == "node" and "entrance" in el.tags:
                    self.inc("out_address_entrance")
                if "entrance" not in el.tags:
                    self.inc("out_address_parcel")

    def cons_stats(self, data, task_label=None):
        for el in data.elements:
            if "leisure" in el.tags and el.tags["leisure"] == "swimming_pool":
                self.inc("out_pools")
                self.inc("out_features")
            if "building" in el.tags:
                self.inc("out_buildings")
                self.building_counter[el.tags["building"]] += 1
                self.inc("out_features")
            if "building:part" in el.tags:
                self.inc("out_parts")
                self.inc("out_features")
            if "fixme" in el.tags:
                self.fixme_counter[el.tags["fixme"]] += 1
                if task_label is not None:
                    self.tasks_with_fixmes.add(task_label)

    def get_tasks_with_fixmes(self):
        return sorted(self.tasks_with_fixmes)

    def osm_stats(self, data):
        self.inc("nodes", len(data.nodes))
        self.inc("ways", len(data.ways))
        self.inc("relations", len(data.relations))

    def cons_end_stats(self):
        self.dlag = ", ".join(
            [
                "%d: %d" % (l, c)
                for (l, c) in list(
                    OrderedDict(Counter(list(self.max_level.values()))).items()
                )
            ]
        )
        self.dlbg = ", ".join(
            [
                "%d: %d" % (l, c)
                for (l, c) in list(
                    OrderedDict(Counter(list(self.min_level.values()))).items()
                )
            ]
        )
        self.building_types = ", ".join(
            ["%s: %d" % (b, c) for (b, c) in list(self.building_counter.items())]
        )

    def fixme_stats(self):
        fixme_count = sum(self.fixme_counter.values())
        if fixme_count:
            self.fixme_count = fixme_count
            self.fixmes = [
                "%s: %d" % (f, c) for (f, c) in list(self.fixme_counter.items())
            ]
        return fixme_count

    def get(self, key, default=0):
        return self.values.get(key, default)

    def inc(self, key, step=1):
        self.values[key] = self.get(key) + step

    def sum(self, *args):
        return sum(self.get(key) for key in args)

    def get_sys_info(self):
        p = psutil.Process()
        v = list(platform.uname())
        v.pop(1)
        self.platform = " ".join(v)
        self.app_version = config.app_name + " " + config.app_version
        self.language = config.language
        self.cpu_count = psutil.cpu_count(logical=False)
        self.cpu_freq = getattr(getattr(psutil, "cpu_freq", lambda: 0)(), "max", 0)
        self.memory = psutil.virtual_memory().total / MEMORY_UNIT
        self.rss = p.memory_info().rss / MEMORY_UNIT
        self.vms = p.memory_info().vms / MEMORY_UNIT

    def clean_group(self, group):
        group = "_" + group
        for k in frozenset(self.values.keys()):
            if k.endswith(group):
                del self.values[k]

    def validate(self):
        if self.sum("tasks_u", "tasks_r") != self.get("tasks"):
            self.errors.append(
                _(
                    "Sum of rustic and urban tasks should be equal "
                    "to number of tasks in the project"
                )
            )
        if self.sum("inp_address_entrance", "inp_address_parcel") != self.get(
            "inp_address"
        ):
            self.errors.append(
                _("Sum of address types should be equal to the input addresses")
            )
        if self.sum(
            "addresses_without_number",
            "not_unique_addresses",
            "multiple_addresses",
            "refused_addresses",
            "ignored_addresses",
            "out_address",
            "pool_addresses",
            "orphaned_addresses",
        ) != self.get("inp_address"):
            self.errors.append(
                _(
                    "Sum of output and deleted addresses should be equal "
                    "to the input addresses"
                )
            )
        if (
            self.sum("out_address_entrance", "out_address_parcel") > 0
            and self.sum("out_address_entrance", "out_address_parcel")
        ) != self.get("out_address"):
            self.errors.append(
                _(
                    "Sum of entrance and parcel addresses should be equal "
                    "to output addresses"
                )
            )
        if self.sum("out_addr_str", "out_addr_plc") != self.get("out_address"):
            self.errors.append(
                _(
                    "Sum of street and place addresses should be equal "
                    "to output addresses"
                )
            )
        if self.sum("inp_buildings", "inp_parts", "inp_pools") != self.get(
            "inp_features"
        ):
            self.errors.append(
                _(
                    "Sum of buildings, parts and pools should be equal "
                    "to the feature count"
                )
            )
        if self.sum(
            "out_features",
            "outside_parts",
            "underground_parts",
            "multipart_geoms_building",
            "parts_to_outline",
            "parts_wo_building",
            "adjacent_parts",
            "geom_invalid_building",
            "buildings_in_pools",
        ) - self.get("exploded_parts_building") != self.get("inp_features"):
            self.errors.append(
                _(
                    "Sum of output and deleted minus created "
                    "building features should be equal to input features"
                )
            )
        if self.building_counter:
            if sum(self.building_counter.values()) != self.get("out_buildings"):
                self.errors.append(
                    _(
                        "Sum of building types should be equal "
                        "to the number of buildings"
                    )
                )

    def to_string(self):
        if self.start_time is not None:
            self.ex_time = time.time() - self.start_time
        groups = set()
        last_group = False
        last_subgroup = False
        for key in list(self.titles.keys()):
            exists = key in self.values
            if (
                exists
                and isinstance(self.values[key], list)
                and len(self.values[key]) == 0
            ):
                exists = False
            if key.startswith("group_"):
                last_group = key
                last_subgroup = False
            elif key.startswith("subgroup_"):
                last_subgroup = key
            if last_group and exists:
                groups.add(last_group)
            if last_subgroup and exists:
                groups.add(last_subgroup)
        output = ""
        for key, title in list(self.titles.items()):
            if title is None:
                continue
            if key.startswith("group_") and key in groups:
                output += config.eol + "=" + self.titles[key] + "=" + config.eol
            elif key.startswith("subgroup_") and key in groups:
                output += config.eol + "==" + self.titles[key] + "==" + config.eol
            elif key in self.values:
                if isinstance(self.values[key], list):
                    if len(self.values[key]) > 0:
                        if title:
                            output += (
                                title
                                + " "
                                + int_format(len(self.values[key]))
                                + config.eol
                            )
                        for value in self.values[key]:
                            output += TAB + value + config.eol
                else:
                    value = self.values[key]
                    if value is None:
                        value = ""
                    if key in self.formats:
                        value = self.formats[key](value)
                    elif isinstance(value, int):
                        value = int_format(value)
                    output += title + SEP + value
                    output += config.eol
        if "fixmes" in self.values:
            output += config.eol + config.fixme_doc_url
        return output

    def to_file(self, fn):
        with io.open(fn, "w", encoding=config.encoding) as fo:
            fo.write(self.to_string())

    def export(self, fn):
        with open(fn, "w") as fo:
            fo.write(json.dumps(self.values))

    def from_file(self, fn):
        with open(fn, "r") as fo:
            self.values = json.loads(fo.read())
            for k, v in self.values.items():
                if k.endswith("_counter"):
                    self.values[k] = Counter(v)


instance = Report()
