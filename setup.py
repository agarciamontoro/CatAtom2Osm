# -*- coding: utf-8 -*-
"""Application preferences"""
from __future__ import unicode_literals
from builtins import range, str, bytes
import six
import sys, os, locale
import csv
import gettext

app_name = 'CatAtom2Osm'
app_version = '1.2dev'
app_author = 'Javier Sánchez Portero'
app_copyright = '2017, Javier Sánchez Portero'
app_desc = 'Tool to convert INSPIRE data sets from the Spanish Cadastre ATOM Services to OSM files'
app_tags = ''

MIN_QGIS_VERSION_INT = 21001
MIN_QGIS_VERSION = '2.10.1'
MIN_GDAL_VERSION_INT = 11103
MIN_GDAL_VERSION = '1.11.3'

def winenv():
    global eol, encoding
    eol = '\n'
    if platform.startswith('win'):
        eol = '\r\n'
        if os.getenv('LANG') is None:
            os.environ['LANG'] = language

def terminal_decode(msg):
    """Decode strings from W$ and Python2"""
    return str(msg) if sys.stdout.encoding == 'utf-8' else \
        bytes(msg, encoding).decode(sys.stdout.encoding)

locale.setlocale(locale.LC_ALL, '')
language, encoding = locale.getdefaultlocale()
app_path = terminal_decode(os.path.dirname(__file__))
localedir = os.path.join(app_path, 'locale', 'po')
platform = sys.platform
winenv()

if six.PY2:
    gettext.install(app_name.lower(), localedir=localedir, unicode=1)
else:
    gettext.install(app_name.lower(), localedir=localedir)
gettext.bindtextdomain('argparse', localedir)
gettext.textdomain('argparse')

log_level = 'INFO' # Default log level
log_file = 'catatom2osm.log'
log_format = '%(asctime)s - %(levelname)s - %(message)s'

fn_prefix = 'A.ES.SDGC' # Inspire Atom file name prefix

silence_gdal = False

delimiter = '\t'
dup_thr = 0.012 # Distance in meters to merge nearest vertexs.
                # 0.011 is about 1E-7 degrees in latitude
dist_thr = 0.02 # Threshold in meters for vertex simplification and topological points.
straight_thr = 2 # Threshold in degrees from straight angle to delete a vertex
acute_thr = 10 # Remove vertices with an angle smaller than this value
min_area = 0.05 # Delete geometries with an area smaller than this value
addr_thr = 10 # Distance in meters to merge address node with building footprint
acute_inv = 5 # Remove geometries/rings that result invalid after removing any vertex with an angle smaller than this value
dist_inv = 0.1 # Threshold in meters to filter angles for zig-zag and spikes
entrance_thr = 0.4 # Minimum distance in meters from a entrance to the nearest corner
warning_min_area = 1 # Area in m2 for small area warning
warning_max_area = 30000 # Area in m2 for big area warning

changeset_tags = {
    'comment': "#Spanish_Cadastre_Buildings_Import",
    'source': u"Dirección General del Catastro",
    'type': 'import',
    'url': "https://wiki.openstreetmap.org/wiki/Spanish_Cadastre/Buildings_Import" 
}

base_url = {
    "BU": "http://www.catastro.minhap.es/INSPIRE/buildings/",
    "AD": "http://www.catastro.minhap.es/INSPIRE/addresses/",
    "CP": "http://www.catastro.minhap.es/INSPIRE/CadastralParcels/"
}

serv_url = {
    "BU": base_url['BU'] + "ES.SDGC.BU.atom.xml",
    "AD": base_url['AD'] + "ES.SDGC.AD.atom.xml",
    "CP": base_url['CP'] + "ES.SDGC.CP.atom.xml"
}

prov_url = {
    "BU": base_url['BU'] + "{code}/ES.SDGC.bu.atom_{code}.xml",
    "AD": base_url['AD'] + "{code}/ES.SDGC.ad.atom_{code}.xml",
    "CP": base_url['CP'] + "{code}/ES.SDGC.CP.atom_{code}.xml"
}

cadastre_doc_url = 'http://ovc.catastro.meh.es/OVCServWeb/OVCWcfLibres/OVCFotoFachada.svc/RecuperarFotoFachadaGet?ReferenciaCatastral={}'

valid_provinces = ["%02d" % i for i in range(2,57) if i not in (20, 31, 48)]

no_number = 'S-N' # Regular expression to match addresses without number

lowcase_words = [ # Words to exclude from the general Title Case rule for highway names
    'DE', 'DEL', 'EL', 'LA', 'LOS', 'LAS', 'Y', 'AL', 'EN',
    'A LA', 'A EL', 'A LOS', 'DE LA', 'DE EL', 'DE LOS', 'DE LAS',
    'ELS', 'LES', "L'", "D'", "N'", "S'", "NA", "DE NA", "SES", "DE SES",
    "D'EN", "D'EL", "D'ES", "DE'N", "DE'L", "DE'S"
]

highway_types_es = { 
    'AG': 'Agregado',
    'AL': 'Aldea/Alameda',
    'AR': 'Área/Arrabal',
    'AU': 'Autopista',
    'AV': 'Avenida',
    'AY': 'Arroyo',
    'BJ': 'Bajada',
    'BO': 'Barrio',
    'BR': 'Barranco',
    'CA': 'Cañada',
    'CG': 'Colegio/Cigarral',
    'CH': 'Chalet',
    'CI': 'Cinturón',
    'CJ': 'Calleja/Callejón',
    'CL': 'Calle',
    'CM': 'Camino/Carmen',
    'CN': 'Colonia',
    'CO': 'Concejo/Colegio',
    'CP': 'Campa/Campo',
    'CR': 'Carretera/Carrera',
    'CS': 'Caserío',
    'CT': 'Cuesta/Costanilla',
    'CU': 'Conjunto',
    'CY': 'Caleya',
    'DE': 'Detrás',
    'DP': 'Diputación',
    'DS': 'Diseminados',
    'ED': 'Edificios',
    'EM': 'Extramuros',
    'EN': 'Entrada/Ensanche',
    'ER': 'Extrarradio',
    'ES': 'Escalinata',
    'EX': 'Explanada',
    'FC': 'Ferrocarril/Finca',
    'FN': 'Finca',
    'GL': 'Glorieta',
    'GR': 'Grupo',
    'GV': 'Gran Vía',
    'HT': 'Huerta/Huerto',
    'JR': 'Jardines',
    'LD': 'Lado/Ladera',
    'LG': 'Lugar',
    'MC': 'Mercado',
    'ML': 'Muelle',
    'MN': 'Município',
    'MS': 'Masías',
    'MT': 'Monte',
    'MZ': 'Manzana',
    'PB': 'Poblado',
    'PD': 'Partida',
    'PJ': 'Pasaje/Pasadizo',
    'PL': 'Polígono',
    'PM': 'Páramo',
    'PQ': 'Parroquia/Parque',
    'PR': 'Prolongación/Continuación',
    'PS': 'Paseo',
    'PT': 'Puente',
    'PZ': 'Plaza',
    'QT': 'Quinta',
    'RB': 'Rambla',
    'RC': 'Rincón/Rincona',
    'RD': 'Ronda',
    'RM': 'Ramal',
    'RP': 'Rampa',
    'RR': 'Riera',
    'RU': 'Rúa',
    'SA': 'Salida',
    'SD': 'Senda',
    'SL': 'Solar',
    'SN': 'Salón',
    'SU': 'Subida',
    'TN': 'Terrenos',
    'TO': 'Torrente',
    'TR': 'Travesía/Transversal',
    'UR': 'Urbanización',
    'VR': 'Vereda',
    'AC': 'Acceso',
    'AD': 'Aldea',
    'BV': 'Bulevar',
    'CZ': 'Calzada',
    'PA': 'Paralela',
    'PC': 'Placeta/Plaça',
    'PG': 'Polígono',
    'PO': 'Polígono',
    'SB': 'Subida',
    'SC': 'Sector',
    'CALLEJON': 'Callejón', 'CANTON': 'Cantón',
    'CIRCUNVALACION': 'Circunvalación', 'GENERICA': 'Genérica',
    'JARDIN': 'Jardín', 'MALECON': 'Malecón', 'RINCON': 'Rincón',
    'PROLONGACION': 'Prolongación', 'TRANSITO': 'Tránsito',
    'TRAVESIA': 'Travesía', 'VIA': 'Vía'
}

highway_types_cat = {
    'AG': 'Agregat',
    'AL': 'Llogaret',
    'AR': 'Àrea/Raval',
    'AU': 'Autopista',
    'AV': 'Avinguda',
    'AY': 'Rierol',
    'BJ': 'Baixada',
    'BO': 'Barri',
    'BR': 'Barranc',
    'CA': 'Camí ramader',
    'CG': 'Col·legi/Cigarral',
    'CH': 'Xalet',
    'CI': 'Cinturó/Ronda',
    'CJ': 'Carreró',
    'CL': 'Carrer',
    'CM': 'Camí',
    'CN': 'Colònia',
    'CO': 'Ajuntament/Col·legi',
    'CP': 'Camp',
    'CR': 'Carretera',
    'CS': 'Mas',
    'CT': 'Costa/Rost',
    'CU': 'Conjunt',
    'CY': 'Carreró',
    'DE': 'Darrere',
    'DP': 'Diputació',
    'DS': 'Disseminats',
    'ED': 'Edificis',
    'EM': 'Extramurs/Raval',
    'EN': 'Entrada/Eixample',
    'ER': 'Extraradi/Raval',
    'ES': 'Escalinata',
    'EX': 'Pla',
    'FC': 'Ferrocarril',
    'FN': 'Finca',
    'GL': 'Rotonda/Plaça',
    'GR': 'Grup',
    'GV': 'Gran Via',
    'HT': 'Hort',
    'JR': 'Jardins',
    'LD': 'Marge/Vessant',
    'LG': 'Lloc',
    'MC': 'Mercat',
    'ML': 'Moll',
    'MN': 'Municipi',
    'MS': 'Masies',
    'MT': 'Muntanya',
    'MZ': 'Illa',
    'PB': 'Poblat',
    'PD': 'Partida',
    'PJ': 'Passatge',
    'PL': 'Polígon',
    'PM': 'Erm',
    'PQ': 'Parròquia/Parc',
    'PR': 'Prolongació/Continuació',
    'PS': 'Passeig',
    'PT': 'Pont',
    'PZ': 'Plaça',
    'QT': 'Quinta',
    'RB': 'Rambla',
    'RC': 'Racó',
    'RD': 'Ronda',
    'RM': 'Branc',
    'RP': 'Rampa',
    'RR': 'Riera',
    'RU': 'Rua',
    'SA': 'Sortida',
    'SD': 'Sender',
    'SL': 'Solar',
    'SN': 'Saló',
    'SU': 'Pujada',
    'TN': 'Terrenys',
    'TO': 'Torrent',
    'TR': 'Travessera',
    'UR': 'Urbanització',
    'VR': 'Sendera',
    'AC': 'Accès',
    'AD': 'Llogaret',
    'BV': 'Bulevard',
    'CZ': 'Calçada',
    'PA': 'Paral·lel',
    'PC': 'Placeta/plaça',
    'PG': 'Polígon',
    'PO': 'Polígon',
    'SB': 'Pujada',
    'SC': 'Sector',
}

place_types_es = [
	'Agregado', 'Aldea', 'Área', 'Barrio', 'Barranco', 'Cañada', 'Colegio', 
	'Cigarral', 'Chalet', 'Concejo', 'Campa', 'Campo', 'Caserío', 'Conjunto', 
	'Diputación', 'Diseminados', 'Edificios', 'Extramuros', 'Entrada', 
	'Ensanche', 'Extrarradio', 'Finca', 'Grupo', 'Huerta', 'Huerto', 
	'Jardines', 'Lugar', 'Mercado', 'Muelle', 'Municipio', 'Masías', 'Monte', 
	'Manzana', 'Poblado', 'Partida', 'Polígono', 'Páramo', 'Parroquia', 'Solar', 
	'Terrenos', 'Urbanización', 'Bulevar', 'Sector'
]
place_types_cat = [
    'Agregat', 'Llogaret', 'Àrea', 'Barri', 'Barranc', 'Camí ramader',
    'Col·legi/Cigarral', 'Xalet', 'Ajuntament/Col·legi', 'Camp', 'Mas',
    'Conjunt', 'Diputació', 'Disseminats', 'Edificis', 'Extramurs', 
    'Entrada', 'Extraradi', 'Finca', 'Grup', 'Hort', 'Jardins', 'Lloc',
    'Mercat', 'Moll', 'Municipi', 'Masies', 'Muntanya', 'Illa', 'Poblat',
    'Partida', 'Polígon', 'Erm', 'Parròquia', 'Solar', 'Terrenys',
    'Urbanització', 'Bulevard', 'Sector'
]

# Dictionary for default 'highway_types.csv'
highway_types = highway_types_es

# List of highway types to translate as place addresses
place_types = place_types_es
remove_place_from_name = [place_types_es[26]]

# List of highway types not to be parsed
excluded_types = ['DS', 'ER']

# Dictionary of name and OSM boundary relation id for know municipalities
# wich fails in get_boundary method.
mun_fails = {
    '07032': ['Maó', '1809102'],
    '07040': ['Palma', '341321'],
    '11042': ['Zahara', '343140'],
    '16176': ['Pozorrubio', '347331'],
    '19178': ['Humanes', '341781'],
    '23043': ['Hornos', '344389'],
    '23086': ['Torre del Campo', '346324'],
    '26004': ['Ajamil', '348189'],
    '26093': ['Mansilla de la Sierra', '345202'],
    '28063': ['Gargantilla del Lozoya y Pinilla de Buitrago', '345009'],
    '29101': ['Montecorto', '7541639'],
    '35010': ['Santa María de Guía de Gran Canaria', '345440'],
    '37252': ['Pereña de la Ribera', '343095'],
    '37367': ['Villarino de los Aires', '340062'],
    '38023': ['San Cristóbal de La Laguna', '345393'],
    '38039': ['Santa Úrsula', '340717'],
    '39103': ['Mancomunidad de Campoo-Cabuérniga', '340042'],
    '44007': ['Alba', '345065'],
    '47047': ['Castroponce', '340763'],
    '47101': ['Muriel', '346973'],
    '47207': ['Villafuerte', '341197'],
    '50030': ['Añón de Moncayo', '342653'],
    '50049': ['Biel', '348008'],
    '51021': ['Fuente-Álamo', '341797'],
    '52024': ['Gijón/Xixón', '345576'],
}

aux_address = {'cdau': ['04', '11', '14', '18', '21', '23', '29', '41']}

