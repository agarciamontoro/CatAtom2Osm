"""
Tool to convert INSPIRE data sets from the Spanish Cadastre ATOM Services to OSM files
"""
from past.builtins import basestring  # qgis/utils.py:744: DeprecationWarning
import io, codecs
import gzip
import logging
import os
import shutil
from collections import defaultdict
from glob import glob

from qgis.core import QgsApplication, QgsGeometry, QgsVectorLayer
import qgis.utils

qgis.utils.uninstallErrorHook()
qgis_utils = getattr(qgis.utils, 'QGis', getattr(qgis.utils, 'Qgis', None))
from osgeo import gdal

from catatom2osm import config, catatom, csvtools, geo, osm, osmxml, overpass
from catatom2osm import cdau  # Used in get_auxiliary_addresses
from catatom2osm.report import instance as report

log = logging.getLogger(config.app_name)
if config.silence_gdal:
    gdal.PushErrorHandler('CPLQuietErrorHandler')

tasks_folder = 'tasks'


class QgsSingleton(QgsApplication):
    """Keeps a unique instance of QGIS for the application (and tests)"""
    _qgs = None

    def __new__(cls):
        if QgsSingleton._qgs is None:
            # Init qGis API
            QgsSingleton._qgs = QgsApplication([], False)
            qgis_prefix = os.getenv('QGISHOME')
            if qgis_prefix:
                QgsApplication.setPrefixPath(qgis_prefix, True)
            QgsApplication.initQgis()
            # sets GDAL to convert xlink references to fields but not resolve
            gdal.SetConfigOption('GML_ATTRIBUTES_TO_OGR_FIELDS', 'YES')
            gdal.SetConfigOption('GML_SKIP_RESOLVE_ELEMS', 'ALL')
        return QgsSingleton._qgs


class CatAtom2Osm(object):
    """
    Main application class for a tool to convert the data sets from the
    Spanish Cadastre ATOM Services to OSM files.
    """

    def __init__(self, a_path, options):
        """
        Constructor.

        Args:
            a_path (str): Directory where the source files are located.
            options (dict): Dictionary of options.
        """
        self.options = options
        self.cat = catatom.Reader(a_path)
        self.path = self.cat.path
        report.clear(options=self.options.args, mun_code=self.cat.zip_code)
        report.sys_info = True
        if report.sys_info:
            report.qgs_version = qgis_utils.QGIS_VERSION
            report.gdal_version = gdal.__version__
            log.debug(_("Initialized QGIS %s API"), report.qgs_version)
            log.debug(_("Using GDAL %s"), report.gdal_version)
        gdal_version_int = int('{:02d}{:02d}{:02d}'.format(
            *list(map(int, gdal.__version__.split('.')))))
        self.highway_names_path = self.cat.get_path('highway_names.csv')
        self.tasks_path = self.cat.get_path(tasks_folder)
        if not os.path.exists(self.tasks_path):
            os.makedirs(self.tasks_path)
        self.get_split()
        self.is_new = not os.path.exists(self.highway_names_path)
        self.source = 'building'
        if self.options.address and not self.options.building:
            self.source = 'address'

    @staticmethod
    def create_and_run(a_path, options):
        app = CatAtom2Osm(a_path, options)
        app.run()
        app.exit()

    @staticmethod
    def get_task_comment(label):
        """Return comment for task with this label"""
        comment = ' '.join((
            config.changeset_tags['comment'],
            report.mun_code,
            report.mun_name,
            label,
        ))
        return comment

    def run(self):
        """Launches the app"""
        if self.options.comment:
            self.add_comments()
            return
        log.info(_("Start processing '%s'"), report.mun_code)
        self.get_parcel()
        self.get_boundary()
        self.get_zoning()
        self.get_building()
        self.process_building()
        self.process_parcel()
        if self.options.address:
            self.read_address()
        self.parcel.delete_void_parcels(getattr(self, self.source))
        self.output_zoning()
        if self.options.zoning:
            return
        if self.options.address and self.is_new:
            self.write_osm(self.address_osm, 'address.osm')
            msg = _("Generated '%s'") % self.highway_names_path
            msg += '. ' + _("Please, check it and run again")
            log.info(msg)
            return
        self.building.reproject()
        self.process_tasks(getattr(self, self.source))
        self.finish()

    def add_comments(self):
        """Recover missing task files metadata after Josm editing."""
        folder = os.path.basename(self.tasks_path)
        report_path = self.cat.get_path('report.txt')
        if not os.path.exists(report_path):
            log.info(_("No report found"))
            return
        report.from_file(report_path)
        tasks = 0
        for fn in os.listdir(self.tasks_path):
            if fn.endswith('.osm') or fn.endswith('.osm.gz'):
                tasks += 1
                label = os.path.basename(fn).split('.')[0]
                data = self.read_osm(folder, fn)
                fixmes = sum([1 for e in data.elements if 'fixme' in e.tags])
                if fixmes > 0:
                    log.warning(_("Check %d fixme tags"), fixmes)
                oldtags = dict(data.tags)
                data.tags.update(config.changeset_tags)
                data.tags['comment'] = self.get_task_comment(label)
                data.tags['generator'] = report.app_version
                if 'building_date' in report.values:
                    data.tags['source:date'] = report.building_date
                if 'address_date' in report.values:
                    data.tags['source:date:addr'] = report.address_date
                if data.tags != oldtags:
                    self.write_osm(data, folder, fn)
        if not tasks:
            log.info(_("No tasks found"))

    def get_split(self):
        """Get boundary file for splitting"""
        self.split = None
        if self.options.split:
            split = geo.BaseLayer(self.options.split, 'zoningsplit', 'ogr')
            if not split.isValid():
                raise IOError("Can't open %s" % self.options.split)
            self.split = geo.PolygonLayer('MultiPolygon', 'split', 'memory')
            q = lambda f, __: f.geometry().wkbType() == geo.types.WKBMultiPolygon
            self.split.append(split, query=q)
            if self.split.featureCount() == 0:
                msg = _("'%s' does not include any zone") % self.options.split
                raise ValueError(msg)

    def get_building(self):
        """Merge building, parts and pools"""
        building_gml = self.cat.read("building")
        self.building = geo.ConsLayer(source_date=building_gml.source_date)
        q = None
        if self.split or self.options.parcel:
            q = lambda f, kw: self.building.get_id(f) in kw['keys']
        self.building.append(building_gml, query=q, keys=self.tasks.keys())
        inbu = self.building.featureCount()
        if inbu == 0:
            del building_gml
            raise ValueError(_("No buildings data"))
        if self.options.address and not self.options.building:
            return
        part_gml = self.cat.read("buildingpart")
        self.building.append(part_gml, query=q, keys=self.tasks.keys())
        inpa = self.building.featureCount() - inbu
        other_gml = self.cat.read("otherconstruction", True)
        if other_gml:
            self.building.append(other_gml, query=q, keys=self.tasks.keys())
        if self.options.building:
            report.building_date = building_gml.source_date
            report.inp_features = self.building.featureCount()
            report.inp_buildings = inbu
            report.inp_parts = inpa
            report.inp_pools = report.inp_features - inbu - inpa

    def process_tasks(self, source):
        """Convert to osm for each task."""
        tasks = self.get_tasks(source)
        tasks_r = 0
        tasks_u = 0
        for pa in self.parcel.getFeatures():
            label = pa['localId']
            task = tasks[label]
            if len(pa['zone']) == 3:
                tasks_r += 1
            else:
                tasks_u += 1
            comment = self.get_task_comment(label)
            task_osm = task.to_osm(upload='yes', tags={'comment': comment})
            if self.options.address and self.options.building:
                 self.merge_address(task_osm, self.address_osm)
            if self.options.address:
                report.address_stats(task_osm)
            if self.options.building:
                report.cons_stats(task_osm, label)
                report.osm_stats(task_osm)
            self.write_osm(task_osm, tasks_folder, label + '.osm.gz')
            del task
        msg = _("Generated %d rustic and %d urban tasks files")
        log.debug(msg, tasks_r, tasks_u)
        report.tasks_r = tasks_r
        report.tasks_u = tasks_u

    def get_tasks(self, source):
        """
        Put each source feature into a task layer according to their localId.
        """
        if os.path.exists(self.tasks_path):
            for fn in os.listdir(self.tasks_path):
                if os.path.isfile(fn):
                    os.remove(os.path.join(self.tasks_path, fn))
        tasks = {}
        layer_class = type(source)
        last_task = None
        to_add = []
        fcount = source.featureCount()
        for i, feat in enumerate(source.getFeatures()):
            localid = source.get_id(feat)
            label = self.tasks.get(localid, localid)
            if i == 0:
                last_task = label
            f = source.copy_feature(feat, {}, {})
            if i == fcount - 1 or label == last_task:
                to_add.append(f)
            if i == fcount - 1 or label != last_task:
                if last_task not in tasks:
                    tasks[last_task] = layer_class(baseName=last_task)
                    tasks[last_task].source_date = source.source_date
                tasks[last_task].writer.addFeatures(to_add)
                to_add = [f]
            last_task = label
        return tasks

    def get_zoning(self):
        """Get zoning data"""
        zoning_gml = self.cat.read("cadastralzoning")
        self.rustic_zoning = geo.ZoningLayer(baseName='rusticzoning')
        self.urban_zoning = geo.ZoningLayer(baseName='urbanzoning')
        q = lambda f, kw: self.urban_zoning.check_zone(f, kw['level'])
        if self.split or self.options.parcel:
            q = lambda f, kw: (
                self.urban_zoning.check_zone(f, kw['level'])
                and self.parcel_query(f, kw)
            )
        self.rustic_zoning.append(zoning_gml, query=q, level='P')
        self.urban_zoning.append(zoning_gml, query=q, level='M')
        del zoning_gml

    def get_boundary(self):
        """Get best boundary search area for overpass queries."""
        fn = os.path.join(config.app_path, 'municipalities.csv')
        __, id, name = csvtools.get_key(fn, self.cat.zip_code)
        self.boundary_search_area = id
        report.mun_name = name
        report.cat_mun = self.cat.cat_mun
        log.info(_("Municipality: '%s'"), name)

    def output_zoning(self):
        """Generates project zoning file"""
        if not self.options.parcel:
            self.parcel.simplify()
            fn = 'zoning.geojson'
            self.export_layer(self.parcel, fn, target_crs_id=4326)
            report.tasks = self.parcel.featureCount()

    def process_building(self):
        """Process all buildings dataset"""
        self.building.remove_outside_parts()
        self.building.remove_parts_wo_building()
        self.building.explode_multi_parts()
        self.building.clean()
        if self.options.building:
            self.building.validate(report.max_level, report.min_level)

    def get_parcel(self):
        """Get parcels dataset"""
        parcel_gml = self.cat.read("cadastralparcel")
        self.parcel = geo.ParcelLayer(self.cat.zip_code)
        self.parcel.source_date = parcel_gml.source_date
        q = None
        if self.split:
            if self.split.crs() != parcel_gml.crs():
                self.split.reproject(parcel_gml.crs())
            q = lambda f, __: self.split.is_inside_area(f)
        elif self.options.parcel:
            localid = self.options.parcel[0]
            try:
                pa = next(parcel_gml.search(f"localId = '{localid}'"))
            except StopIteration:
                msg = _("Parcel '%s' does not exists") % localid
                raise(ValueError(msg))
            bb = pa.geometry().boundingBox().buffered(config.parcel_buffer)
            g = QgsGeometry.fromRect(bb)
            q = lambda f, __: geo.aux.is_inside(f, g)
        self.parcel_query = q
        self.parcel.append(parcel_gml, query=q)
        del parcel_gml
        if self.parcel.featureCount() == 0:
            raise ValueError(_("No parcels data"))
        self.tasks = {
            f['localId']: f['localId'] for f in self.parcel.getFeatures()
        }

    def process_parcel(self):
        """Process parcels dataset"""
        self.parcel.delete_void_parcels(self.building)
        self.parcel.clean()
        self.parcel.create_missing_parcels(self.building)
        self.parcel.set_zones(self.urban_zoning)
        self.parcel.set_zones(self.rustic_zoning)
        self.parcel.set_missing_zones()
        tasks1 = self.parcel.merge_by_adjacent_buildings(self.building)
        for k, v in self.tasks.items():
            self.tasks[k] = tasks1.get(v, v)
        tasks2 = self.parcel.merge_by_parts_count(
            config.parcel_parts, config.parcel_dist
        )
        for k, v in self.tasks.items():
            self.tasks[k] = tasks2.get(v, v)


    def finish(self):
        """Generates final report"""
        options = self.options
        if report.fixme_stats():
            log.warning(_("Check %d fixme tags"), report.fixme_count)
            fn = 'review.txt'
            with open(self.cat.get_path(fn), "w") as fo:
                fixmes = report.get_tasks_with_fixmes()
                fo.write(config.eol.join(fixmes) + config.eol
                )
                log.info(
                    _("Generated '%s'") + '. ' + _("Please, check it"), fn
                )
        if options.building:
            report.cons_end_stats()
        else:
            report.clean_group('building')
        report.to_file(self.cat.get_path('report.txt'))
        self.move_project()
        log.info(_("Finished!"))

    def exit(self):
        """Ends properly"""
        for propname in list(self.__dict__.keys()):
            if isinstance(getattr(self, propname), QgsVectorLayer):
                delattr(self, propname)

    def read_address(self):
        """Reads Address GML dataset"""
        address_gml = self.cat.read("address")
        report.address_date = address_gml.source_date
        if address_gml.writer.fieldNameIndex('component_href') == -1:
            address_gml = self.cat.read("address", force_zip=True)
            if address_gml.writer.fieldNameIndex('component_href') == -1:
                msg = _(
                    "Could not resolve joined tables for the '%s' layer"
                ) % address_gml.name()
                raise IOError(msg)
        self.address = geo.AddressLayer(source_date=address_gml.source_date)
        q = None
        if self.split or self.options.parcel:
            q = lambda f, kw: self.address.get_id(f) in kw['keys']
            self.boundary_bbox = self.parcel.bounding_box()
        self.address.append(address_gml, query=q, keys=self.tasks.keys())
        del address_gml
        report.inp_address = self.address.featureCount()
        report.inp_address_entrance = self.address.count("spec='Entrance'")
        report.inp_address_parcel = self.address.count("spec='Parcel'")
        self.address.remove_address_wo_building(self.building)
        if report.inp_address == 0:
            msg = _("No addresses data")
            if not self.options.building:
                raise ValueError(msg)
            log.info(msg)
            return
        postaldescriptor = self.cat.read("postaldescriptor")
        thoroughfarename = self.cat.read("thoroughfarename")
        self.address.join_field(
            postaldescriptor, 'PD_id', 'gml_id', ['postCode']
        )
        self.address.join_field(
            thoroughfarename, 'TN_id', 'gml_id', ['text'], 'TN_'
        )
        del postaldescriptor, thoroughfarename
        report.inp_zip_codes = self.address.count(unique='postCode')
        report.inp_street_names = self.address.count(unique='TN_text')
        self.get_auxiliary_addresses()
        self.export_layer(self.address, 'address.geojson', target_crs_id=4326)
        highway_names = self.get_translations(self.address)
        ia = self.address.translate_field('TN_text', highway_names)
        if ia > 0:
            log.debug(_("Deleted %d addresses refused by street name"), ia)
            report.values['ignored_addresses'] = ia
        if not self.is_new and not self.options.manual:
            current_address = self.get_current_ad_osm()
            self.address.conflate(current_address)
        self.building.move_address(self.address)
        self.address.reproject()
        self.address_osm = self.address.to_osm()

    def get_auxiliary_addresses(self):
        """If exists, reads and conflate an auxiliary addresses data source"""
        for source in list(config.aux_address.keys()):
            if self.cat.zip_code[:2] in config.aux_address[source]:
                aux_source = globals()[source]
                aux_path = os.path.join(
                    os.path.dirname(self.path), config.aux_path
                )
                reader = aux_source.Reader(aux_path)
                aux = reader.read(self.cat.zip_code[:2])
                aux_source.conflate(aux, self.address, self.cat.zip_code)

    def merge_address(self, building_osm, address_osm):
        """
        Copy address from address_osm to building_osm using 'ref' tag.

        If there exists one building with the same 'ref' that an address, copy
        the address tags to the building if it isn't a 'entrace' type address or
        else to the entrance if there exist a node with the address coordinates
        in the building.

        Precondition: building.move_address deleted addresses belonging to multiple buildings

        Args:
            building_osm (Osm): OSM data set with buildings
            address_osm (Osm): OSM data set with addresses
        """
        if 'source:date' in address_osm.tags:
            building_osm.tags['source:date:addr'] = address_osm.tags[
                'source:date']
        address_index = defaultdict(list)
        building_index = defaultdict(list)
        for bu in building_osm.elements:
            if 'ref' in bu.tags:
                building_index[bu.tags['ref']].append(bu)
        for ad in address_osm.nodes:
            if ad.tags['ref'] in building_index:
                address_index[ad.tags['ref']].append(ad)
        md = 0
        for (ref, group) in list(building_index.items()):
            parcel_ad = []
            entrance_count = 0
            for ad in address_index[ref]:
                entrance = False
                if 'entrance' in ad.tags:
                    for w in building_osm.get_outline(group):
                        entrance = w.search_node(ad.x, ad.y)
                        if entrance:
                            ad.tags['group'] = str(len(group))
                            entrance.tags.update(ad.tags)
                            entrance.tags.pop('ref', None)
                            entrance.tags.pop('image', None)
                            break
                if entrance:
                    entrance_count += 1
                else:
                    parcel_ad.append(ad)
            if len(parcel_ad) == 1 and entrance_count == 0:
                ad = parcel_ad.pop()
                bu = group[0]
                bu.tags.update(ad.tags)
                bu.tags.pop('image', None)
                bu.tags.pop('entrance', None)
            md += len(parcel_ad)
        if md > 0:
            log.debug(
                _("Refused %d 'parcel' addresses not unique for it building"),
                md)
            report.inc('not_unique_addresses', md)

    def get_translations(self, address):
        """
        If there exists the configuration file 'highway_types.csv', read it,
        else write one with default values. If don't exists the translations file
        'highway_names.csv', creates one parsing current OSM highways data, else
        reads and returns it as a dictionary.

        * 'highway_types.csv' List of osm elements in json format located in the
          application path that contains translations from abbreviations to full
          types of highways.

        * 'highway_names.csv' is located in the outputh folder and contains
          corrections for original highway names.
        """
        highway_types_path = os.path.join(config.app_path, 'highway_types.csv')
        if not os.path.exists(highway_types_path):
            csvtools.dict2csv(highway_types_path, config.highway_types)
        else:
            csvtools.csv2dict(highway_types_path, config.highway_types)
        if self.is_new:
            if self.options.manual:
                highway = None
            else:
                highway = self.get_highway()
                highway.reproject(address.crs())
            highway_names = address.get_highway_names(highway)
            csvtools.dict2csv(self.highway_names_path, highway_names, sort=1)
        else:
            highway_names = csvtools.csv2dict(self.highway_names_path, {})
        for key, value in list(highway_names.items()):
            highway_names[key] = value.strip()
        return highway_names

    def get_highway(self):
        """Gets OSM highways needed for street names conflation"""
        ql = ['way["highway"]["name"]',
              'relation["highway"]["name"]',
              'way["place"="square"]["name"]',
              'relation["place"="square"]["name"]']
        highway_osm = self.read_osm('current_highway.osm', ql=ql)
        highway = geo.HighwayLayer()
        highway.read_from_osm(highway_osm)
        del highway_osm
        return highway

    def get_current_ad_osm(self):
        """Gets OSM address for address conflation"""
        ql = [
            'node["addr:street"]["addr:housenumber"]["entrance"]',
            'wr["addr:street"]["addr:housenumber"][~"building"~".*"]',
            'nwr["addr:place"]["addr:housenumber"]',
        ]
        address_osm = self.read_osm('current_address.osm', ql=ql)
        current_address = set()
        w = 0
        report.osm_addresses = 0
        for d in address_osm.elements:
            if 'addr:housenumber' not in d.tags:
                if 'addr:street' in d.tags or 'addr:place' in d.tags:
                    w += 1
            elif 'addr:street' in d.tags:
                current_address.add(
                    d.tags['addr:street'] + d.tags['addr:housenumber'])
                report.osm_addresses += 1
            elif 'addr:place' in d.tags:
                current_address.add(
                    d.tags['addr:place'] + d.tags['addr:housenumber'])
                report.osm_addresses += 1
        if w > 0:
            msg = _(
                "There are %d address without house number in the OSM data") % w
            log.warning(msg)
            report.warnings.append(msg)
            report.osm_addresses_without_number = w
        return current_address

    def move_project(self):
        """
        Move to tasks all files needed for the project for backup in the
        repository. Use a subdirectory if it's a split municipality.
        """
        fn = self.options.split or ''
        bkp_dir = os.path.splitext(os.path.basename(fn))[0]
        bkp_path = self.cat.get_path(tasks_folder, bkp_dir)
        if not os.path.exists(bkp_path):
            os.makedirs(bkp_path)
        move_files = [
            'current_address.osm', 'current_highway.osm', 'highway_names.csv'
        ]
        copy_files = [
            'address.osm', 'address.geojson', 'report.txt', 'review.txt',
            'zoning.geojson'
        ]
        if self.options.split:
            copy_files.append(self.options.split)
        for f in move_files:
            fn = self.cat.get_path(f)
            if os.path.exists(fn):
                os.rename(fn, os.path.join(bkp_path, f))
        for f in copy_files:
            fn = self.cat.get_path(f)
            if os.path.exists(fn):
                shutil.copy(fn, bkp_path)

    def export_layer(
        self, layer, filename, driver_name='GeoJSON', target_crs_id=None
    ):
        """
        Export a vector layer.

        Args:
            layer (QgsVectorLayer): Source layer.
            filename (str): Output filename.
            driver_name (str): Defaults to ESRI Shapefile.
            target_crs_id (int): Defaults to source CRS.
        """
        out_path = self.cat.get_path(filename)
        if layer.export(out_path, driver_name, target_crs_id=target_crs_id):
            log.info(_("Generated '%s'"), filename)
        else:
            raise IOError(_("Failed to write layer: '%s'") % filename)

    def read_osm(self, *paths, **kwargs):
        """
        Reads a OSM data set from a OSM XML file. If the file not exists,
        downloads data from overpass using ql query

        Args:
            paths (str): input filename components relative to self.path
            ql (str): Query to put in the url for overpass

        Returns
            Osm: OSM data set
        """
        ql = kwargs.get('ql', False)
        osm_path = self.cat.get_path(*paths)
        filename = os.path.basename(osm_path)
        if not os.path.exists(osm_path):
            if not ql:
                return None
            log.info(_("Downloading '%s'") % filename)
            query = overpass.Query(self.boundary_search_area)
            if hasattr(self, 'boundary_bbox') and self.boundary_bbox:
                query.set_search_area(self.boundary_bbox)
            query.add(ql)
            if log.app_level == logging.DEBUG:
                query.download(osm_path, log)
            else:
                query.download(osm_path)
        if osm_path.endswith('.gz'):
            fo = gzip.open(osm_path, 'rb')
        else:
            fo = open(osm_path, 'rb')
        data = osmxml.deserialize(fo)
        fo.close()
        if len(data.elements) == 0:
            msg = _("No OSM data were obtained from '%s'") % filename
            log.warning(msg)
            report.warnings.append(msg)
        else:
            log.info(_("Read '%s': %d nodes, %d ways, %d relations"),
                     filename, len(data.nodes), len(data.ways),
                     len(data.relations))
        return data

    def write_osm(self, data, *paths):
        """
        Generates a OSM XML file for a OSM data set.

        Args:
            data (Osm): OSM data set
            paths (str): output filename components relative to self.path
                            (compress if ends with .gz)
        """
        for e in data.elements:
            if 'ref' in e.tags:
                del e.tags['ref']
        data.merge_duplicated()
        osm_path = self.cat.get_path(*paths)
        if osm_path.endswith('.gz'):
            file_obj = codecs.getwriter("utf-8")(gzip.open(osm_path, "w"))
        else:
            file_obj = io.open(osm_path, "w", encoding="utf-8")
        osmxml.serialize(file_obj, data)
        file_obj.close()
        msg = _("Generated '%s': %d nodes, %d ways, %d relations")
        log.info(
            msg, os.path.basename(osm_path), len(data.nodes), len(data.ways),
            len(data.relations),
        )

