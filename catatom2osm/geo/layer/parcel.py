import logging
from collections import defaultdict

from qgis.core import (
    QgsFeature, QgsFeatureRequest, QgsField, QgsGeometry, QgsRectangle
)
from qgis.PyQt.QtCore import QVariant

from catatom2osm import config
from catatom2osm.geo.aux import get_attributes, is_inside_area, merge_groups
from catatom2osm.geo.geometry import Geometry
from catatom2osm.geo.layer.cons import ConsLayer
from catatom2osm.geo.layer.polygon import PolygonLayer

log = logging.getLogger(config.app_name)


class ParcelLayer(PolygonLayer):
    """Class for cadastral parcels"""

    def __init__(
        self,
        mun_code,
        path="MultiPolygon",
        baseName="cadastralparcel",
        providerLib="memory",
        source_date=None,
    ):
        super(ParcelLayer, self).__init__(path, baseName, providerLib)
        if self.fields().isEmpty():
            self.writer.addAttributes([
                QgsField('localId', QVariant.String, len=14),
                QgsField('parts', QVariant.Int),
                QgsField('zone', QVariant.String, len=5),
            ])
            self.updateFields()
        self.mun_code = mun_code
        self.rename = {'localId': 'inspireId_localId'}
        self.source_date = source_date
        self.mun_code = mun_code

    def delete_void_parcels(self, buildings):
        """Remove parcels without buildings (or pools)."""
        exp = "NOT(localId ~ 'part')"
        bu_refs = [ConsLayer.get_id(f) for f in buildings.search(exp)]
        to_clean = [
            f.id() for f in self.getFeatures() if f['localId'] not in bu_refs
        ]
        if to_clean:
            self.writer.deleteFeatures(to_clean)
            log.debug(_("Removed %d void parcels"), len(to_clean))

    def create_missing_parcels(self, buildings):
        """Creates fake parcels for buildings not contained in any."""
        pa_refs = [f['localId'] for f in self.getFeatures()]
        to_add = {}
        exp = "NOT(localId ~ 'part')"
        for bu in buildings.getFeatures(exp):
            ref = buildings.get_id(bu)
            if ref not in pa_refs:
                mp = Geometry.get_outer_rings(bu)
                bu_geom = Geometry.fromMultiPolygonXY(mp)
                if ref in to_add:
                    parcel = to_add[ref]
                    pa_geom = bu_geom.combine(parcel.geometry())
                    parcel.setGeometry(pa_geom)
                else:
                    parcel = QgsFeature(self.fields())
                    parcel['localId'] = ref
                    parcel.setGeometry(bu_geom)
                to_add[ref] = parcel
        if to_add:
            self.writer.addFeatures(to_add.values())
            log.debug(_("Added %d missing parcels"), len(to_add))

    def set_zones(self, zoning):
        """
        Assigns to each parcel the label of the zone that contains it
        """
        index = zoning.get_index()
        features = {f.id(): f for f in zoning.getFeatures()}
        to_change = {}
        pbar = self.get_progressbar(_("setzones"), self.featureCount())
        for pa in self.getFeatures():
            if pa['zone'] is None:
                c = pa.geometry().centroid()
                fid = index.nearestNeighbor(c, 1)[0]
                zone = features[fid]
                label = zoning.format_label(zone)
                pa_label = self.get_zone(pa)
                if pa_label == label or is_inside_area(pa, zone):
                    pa['zone'] = label
                    to_change[pa.id()] = get_attributes(pa)
            pbar.update()
        pbar.close()
        log.info("%d", len(to_change))
        if to_change:
            self.writer.changeAttributeValues(to_change)

    def get_groups_by_adjacent_buildings(self, buildings):
        """
        Get grupos of ids of parcels with buildings sharing walls with
        buildings of another parcel.
        """
        exp = "NOT(localId ~ 'part')"
        bu_groups, __ = buildings.get_contacts_and_geometries(exp)
        bu_refs = {f.id(): ConsLayer.get_id(f) for f in buildings.search(exp)}
        geometries = {}
        pa_ids = {}
        pa_refs = {}
        pa_zone = {}
        for f in self.getFeatures():
            geometries[f.id()] = QgsGeometry(f.geometry())
            pa_ids[f['localId']] = f.id()
            pa_refs[f.id()] = f['localId']
            pa_zone[f.id()] = self.get_zone(f)
        adjs = defaultdict(list)
        for group in bu_groups:
            pids = set()
            for bid in group:
                ref = bu_refs[bid]
                pids.add(pa_ids[ref])
            k = '-'.join(set([pa_zone[fid] for fid in pids]))
            adjs[k].append(pids)
        mz_groups = {k for k in adjs.keys() if '-' in k}
        mz_groups |= {z for k in mz_groups for z in k.split('-')}
        pa_groups = merge_groups([adj for z in mz_groups for adj in adjs[z]])
        for z, adj in adjs.items():
            if z not in mz_groups:
                if len(adj) == 1:
                    pa_groups.append(adj[0])
                else:
                    for group in merge_groups(adj):
                        pa_groups.append(group)
        return pa_groups, pa_refs, geometries

    def update_parts_count(self, pa_groups, pa_refs, parts_count):
        tasks = {}
        self.startEditing()
        for group in pa_groups:
            pc = 0
            targetid = pa_refs[group[0]]
            for fid in group:
                localid = pa_refs[fid]
                tasks[localid] = targetid
                pc += parts_count[localid]
            fnx = self.writer.fieldNameIndex('parts')
            self.changeAttributeValue(group[0], fnx, pc)
        self.commitChanges()
        return tasks

    def merge_by_adjacent_buildings(self, buildings):
        """
        Merge parcels with buildings sharing walls with buildings of another
        parcel.
        """
        parts_count = self.count_parts(buildings)
        pa_groups, pa_refs, geometries = (
            self.get_groups_by_adjacent_buildings(buildings)
        )
        area = lambda fid: geometries[fid].area()
        self.merge_geometries(pa_groups, geometries, area, True, False)
        tasks = self.update_parts_count(pa_groups, pa_refs, parts_count)
        return tasks

    def count_parts(self, buildings):
        """Adds count of parts in parcel field"""
        parts_count = defaultdict(int)
        for f in buildings.getFeatures():
            parts_count[buildings.get_id(f)] += 1
        to_change = {}
        for f in self.getFeatures():
            f['parts'] = parts_count[f['localId']]
            to_change[f.id()] = get_attributes(f)
        self.writer.changeAttributeValues(to_change)
        return dict(parts_count)

    def get_zone(self, feat):
        zone = feat['zone']
        if zone is None:
            localid = feat['localId']
            zone = localid[0:5]
            if zone == self.mun_code:
                zone = localid[6:9]
        return zone

    def get_groups_by_parts_count(self, max_parts, buffer):
        """
        Get groups of ids of near parcels with less than max_parts
        """
        parts_count = {}
        geometries = {}
        pa_refs = {}
        zoning = defaultdict(list)
        for pa in self.getFeatures():
            geometries[pa.id()] = QgsGeometry(pa.geometry())
            parts_count[pa['localId']] = pa['parts']
            pa_refs[pa.id()] = pa['localId']
            zoning[self.get_zone(pa)].append(pa.id())
        pa_groups = []
        visited = []
        for pa in self.getFeatures():
            if pa.id() in visited:
                continue
            pc = pa['parts']
            geom = geometries[pa.id()]
            centro = geom.centroid()
            distance = lambda fid: centro.distance(geometries[fid].centroid())
            label = self.get_zone(pa)
            candidates = [
                fid for fid in zoning[label]
                if parts_count[pa_refs[fid]] <= max_parts - pc
                and distance(fid) < buffer
            ]
            candidates = sorted(candidates, key=distance)
            group = []
            pcsum = 0
            for fid in candidates:
                pc = parts_count[pa_refs[fid]]
                if pcsum + pc <= max_parts and fid not in visited:
                    visited.append(fid)
                    group.append(fid)
                    pcsum += pc
            if group:
                pa_groups.append(group)
        return pa_groups, pa_refs, geometries, parts_count

    def merge_by_parts_count(self, max_parts, buffer):
        """Merge parcels in groups with less than max_parts"""
        pa_groups, pa_refs, geometries, parts_count = (
            self.get_groups_by_parts_count(max_parts, buffer)
        )
        self.merge_geometries(pa_groups, geometries, None, False, False)
        tasks = self.update_parts_count(pa_groups, pa_refs, parts_count)
        return tasks

    def clean(self):
        """Delete invalid geometries and close vertices, add topological points
        and simplify vertices."""
        self.merge_adjacent_polygons()
        self.delete_invalid_geometries()
        self.topology()
        self.simplify()
