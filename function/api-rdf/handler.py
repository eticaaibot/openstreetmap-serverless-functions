#!/usr/bin/env python3
# ==============================================================================
#
#          FILE:  osmrdf2023.py
#
#         USAGE:  # this is a library. Import into your code:
#                     from osmrdf2022 import *
#
#   DESCRIPTION:  ---
#
#       OPTIONS:  ---
#
#  REQUIREMENTS:  - python3
#                   - lxml
#          BUGS:  - No big XML dumps output format support (not yet)
#                 - No support for PBF Format (...not yet)
#         NOTES:  ---
#       AUTHORS:  Emerson Rocha <rocha[at]ieee.org>
# COLLABORATORS:  ---
#       LICENSE:  Public Domain dedication or Zero-Clause BSD
#                 SPDX-License-Identifier: Unlicense OR 0BSD
#       VERSION:  v0.3.0
#       CREATED:  2022-11-25 19:22:00Z v0.1.0 started
#      REVISION:  2022-11-26 20:47:00Z v0.2.0 node, way, relation basic turtle,
#                                      only attached tags (no <nd> <member> yet)
#                 2022-12-21 01:46:00Z v0.3.0 osmrdf2022.py -> osmrdf2023.py
# ==============================================================================

import os
import sys
from typing import List, Type
import xml.etree.ElementTree as XMLElementTree
from lxml import etree

import requests
import requests_cache

# See also: https://wiki.openstreetmap.org/wiki/Sophox#How_OSM_data_is_stored
# See also https://wiki.openstreetmap.org/wiki/Elements
RDF_TURTLE_PREFIXES = [
    'PREFIX geo: <http://www.opengis.net/ont/geosparql#>',
    'PREFIX osmnode: <https://www.openstreetmap.org/node/>',
    'PREFIX osmrel: <https://www.openstreetmap.org/relation/>',
    'PREFIX osmway: <https://www.openstreetmap.org/way/>',
    'PREFIX osmm: <https://example.org/todo-meta/>',
    'PREFIX osmt: <https://wiki.openstreetmap.org/wiki/Key:>',
    'PREFIX osmx: <https://example.org/todo-xref/>',
    'PREFIX wikidata: <http://www.wikidata.org/entity/>',
    'PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>',
]

OSM_ELEMENT_PREFIX = {
    'node': 'osmnode:',
    'relation': 'osmrel:',
    'tag': 'osmt:',
    'way': 'osmway:'
}

# Using Sophox
OSM_ELEMENT_TYPE_LITERAL = {
    'node': 'n',
    'way': 'w',
    'rel': 'r'
}

# Undocumented
# - osmx:hasnodes
# - osmx:hasmembers
# - osmx:hasrole{CUSTOM}

# @SEE blank nodes https://www.w3.org/TR/turtle/#h2_sec-examples


class OSMApiv06Xml:
    """OSMApiv06Xml

    Not so optimized quick parser for XML files that can fit into memory
    """

    iterator: None
    xmlroot: None  # xml.etree.ElementTree.Element
    root_tag: str  # Example: osm
    root_attrib: dict
    child_1_tag: str
    child_1_attr: dict
    # @TODO for full dumps, will have 1-n child items

    def __init__(self, file_or_string: str) -> None:

        # @TODO maybe eventually implement from file (the large ones)
        # self.iterator = XMLElementTree.iterparse(
        #     source=file_or_string,
        #     events=('start', 'end')
        # )

        # self.iterator = XMLElementTree.fromstring(
        #     file_or_string,
        #     events=('start', 'end')
        # )
        root = XMLElementTree.fromstring(file_or_string)
        self.xmlroot = root
        self.root_tag = root.tag
        self.root_attrib = root.attrib

    def node(self):

        for child in self.xmlroot:
            # print('>>>>> el', child.tag, child.attrib)
            # print('>>>>> el tags', child.findall("tag"))
            xml_tags = None
            _eltags = child.findall("tag")
            if _eltags:
                xml_tags = []
                for item in _eltags:
                    xml_tags.append((item.attrib['k'], item.attrib['v']))
            # print('>>>>> el nd', child.findall("nd"))
            xml_nds = None
            _elnds = child.findall("nd")
            if _elnds:
                xml_nds = []
                for item in _elnds:
                    xml_nds.append(int(item.attrib['ref']))

            xml_members = None
            _elmembers = child.findall("member")
            if _elmembers:
                xml_members = []
                for item in _elmembers:
                    # @FIXME this is incomplete
                    _type = item.attrib['type']
                    _ref = int(item.attrib['ref'])
                    _role = item.attrib['role'] if 'role' in item.attrib else None
                    xml_members.append((_type, _ref, _role))
            # print('>>>>> el2', dict(child.attrib))
            # # @TODO restrict here to node, way, relation, ...
            # print('>>>>> el3', OSMElement(
            #     child.tag, dict(child.attrib)).__dict__)
            return OSMElement(
                child.tag,
                dict(child.attrib),
                xml_tags,
                xml_nds,
                xml_members
            )
            break


class OSMElement:
    """OSMElement generic container for primitives

    Note: this will not do additional checks if input data is valid
    """
    _basegroup: str
    _tag: str
    _el_osm_tags: List[tuple]
    _el_osm_nds: List[int]
    _el_osm_members: List[tuple]
    _xml_filter: Type['OSMElementFilter']
    _tagcaster: Type['OSMElementTagValueCast']
    id: int
    changeset: int
    timestamp: str  # maybe chage later
    user: str
    userid: str
    version: str
    visible: bool
    lat: float
    lon: float

    def __init__(
        self, tag: str, meta: dict,
        xml_tags: List[tuple] = None,
        xml_nds: List[int] = None,
        xml_members: List[tuple] = None,
        xml_filter: Type['OSMElementFilter'] = None,
        tagcaster: Type['OSMElementTagValueCast'] = None,
    ):
        if not isinstance(meta, dict):
            meta = dict(meta)

        self.id = int(meta['id']) if 'id' in meta else None

        # self.version = float(meta['version']) if 'version' in meta else None
        self.version = meta['version'] if 'version' in meta else None
        self.changeset = int(
            meta['changeset']) if 'changeset' in meta else None

        self.timestamp = meta['timestamp'] if 'timestamp' in meta else None

        self.user = meta['user'] if 'user' in meta else None

        # uid = userid
        self.userid = int(meta['uid']) if 'uid' in meta else None
        self.lat = float(meta['lat']) if 'lat' in meta else None
        self.lon = float(meta['lon']) if 'lon' in meta else None

        self._tag = tag
        self._basegroup = '{0}{1}'.format(
            OSM_ELEMENT_PREFIX[tag], str(self.id))

        self._el_osm_tags = xml_tags
        self._el_osm_nds = xml_nds
        self._el_osm_members = xml_members
        self._xml_filter = xml_filter
        self._tagcaster = tagcaster

    def can_output(self) -> bool:
        if not self._xml_filter.can_tag(self._tag):
            return False
        return True

    def to_ttl(self) -> list:
        data = []
        data.append(self._basegroup)

        if self.changeset:
            data.append(f'    osmm:changeset {self.changeset} ;')
        if self.lat and self.lon:
            data.append(
                f'    osmm:loc "Point({self.lat} {self.lon})"^^geo:wktLiteral ;')
        if self.timestamp:
            data.append(
                f'    osmm:timestamp "{self.timestamp}"^^xsd:dateTime ;')
        if self._tag in OSM_ELEMENT_TYPE_LITERAL.keys():
            data.append(
                f'    osmm:type "{OSM_ELEMENT_TYPE_LITERAL[self._tag]}" ;')
        if self.user:
            data.append(
                f'    osmm:user "{self.user}" ;')
        if self.userid:
            data.append(
                f'    osmm:userid {self.userid} ;')
        if self.version:
            data.append(
                f'    osmm:version {self.version} ;')

        # data.append('    # TODO implement the tags')

        if self._el_osm_tags:
            for key, value in self._el_osm_tags:
                _escp_key = osmrdf_tagkey_encode(key)

                data.append(
                    f'    osmt:{_escp_key} "{value}" ;')

                if self._tagcaster and self._tagcaster.can_cast(_escp_key):
                    data.append(self._tagcaster.to_ttl(_escp_key, value))

        if self._el_osm_nds:
            _parts = []
            for ref in self._el_osm_nds:
                _parts.append(f'osmnode:{ref}')
            data.append(
                f'    osmx:hasnodes ({" ".join(_parts)}) ;')

        if self._el_osm_members:
            _parts = []
            for _type, _ref, _role in self._el_osm_members:
                _prefix = OSM_ELEMENT_PREFIX[_type]

                _parts.append(f'[osmx:hasrole{_role} {_prefix}{_ref}]')
            data.append(
                f'    osmx:hasmembers ({" ".join(_parts)}) ;')

        data.append('.')
        return data


class OSMElementFilter:
    """Helper for OSMElement limit what to output
    """

    xml_tags: List = None
    xml_tags_not: List = None

    def __init__(self) -> None:
        pass

    def set_filter_xml_tags(self, tags: list):
        self.xml_tags = tags
        return self

    def set_filter_xml_tags_not(self, tags: list):
        self.xml_tags_not = tags
        return self

    def can_tag(self, tag: str) -> bool:
        if not self.xml_tags and not self.xml_tags_not:
            return True
        if (not self.xml_tags or tag in self.xml_tags) and \
                (not self.xml_tags_not or tag not in self.xml_tags_not):
            return True
        return False


class OSMElementTagger:
    """Poor man's tagger (no external inference required)

    @example
+	<way>	*	is_in=BRA
-	<node>|<way>|<relation>	*	created_by=*
+	<way>|<relation>	*	shacl:lessThanOrEquals:maxspeed=120
    """
    rules: list = None

    def __init__(self, rules=None) -> None:
        # if rules:
        # self.rules =
        if rules:
            self.parse_rules(rules)

    def parse_rules(self, rules_tsv: str):
        parts = rules_tsv.splitlines()
        # print('todooo')
        try:
            rules = []
            for index, line in enumerate(parts):
                line = line.split("\t")
                # print(line)
                _op = line[0]
                _xml_tag = line[1].replace('<', '').replace('>', '').split('|')
                _xml_attrs = line[2]
                # print(line[3])
                _xml_c_attr_key, _xml_c_attr_value = line[3].split('=')
                # _xml_c_attr_key, _xml_c_attr_value = ['', '']
                if _xml_tag[0] == '*':
                    _xml_tag = None
                if _xml_attrs[0] == '*':
                    _xml_attrs = None
                rules.append({
                    'i': index,
                    'op': _op,
                    'xt': _xml_tag,
                    'xa': _xml_attrs,
                    'xack': _xml_c_attr_key,
                    'xacv': _xml_c_attr_value,
                })
            if rules:
                self.rules = rules
        except Exception as err:
            print(f"ERROR OSMElementTagger: {err}")
            print('--- start of file ---')
            print(rules_tsv)
            print('--- end of file ---')
            sys.exit()
            pass

        # print(rules_tsv, self.rules)
        # sys.exit()

    def retag(self, element: str, de_facto_tags: List[tuple] = None):
        new_tags = de_facto_tags
        if self.rules:
            new_tags_temp = []
            left_rules = list(range(0, len(self.rules)))
            # print(left_rules, len(self.rules))
            for rule in self.rules:
                if rule['xt'] is not None and element not in rule['xt']:
                    left_rules.remove(rule['i'])
                    continue
                # TODO implement attribute check
                # new_tags_temp = new_tags
                new_tags_temp = []
                for tag_key, tag_value in new_tags:
                    if rule['op'] == '-':
                        if tag_key in rule['xack']:
                            left_rules.remove(rule['i'])
                            continue
                    if rule['op'] == '+':
                        if tag_key in rule['xack']:
                            tag_value = rule['xacv']
                            left_rules.remove(rule['i'])
                            break
                        else:
                            pass
                            # continue
                    new_tags_temp.append((tag_key, tag_value))
            new_tags = new_tags_temp
            if len(left_rules) > 0:
                for rule_index in left_rules:
                    if self.rules[rule_index]['op'] == '+':
                        # print('TODO add ', self.rules[rule_index])
                        new_tags.append(
                            (self.rules[rule_index]['xack'], self.rules[rule_index]['xacv']))
                        # pass
                    # raise SyntaxError(self.rules[rule_index]['op'])
                pass
        # if element == 'relation':
        #     print('todo', element, de_facto_tags,
        #           self.rules, new_tags_temp, left_rules)
            # sys.exit()
        return new_tags


class OSMElementTagValueCast:
    """Coerse value of vanilla OpenStreetMap tags
    """
    rules: list = None

    def __init__(self, rules=None) -> None:
        # if rules:
        # self.rules =
        if rules:
            self.parse_rules(rules)

    def parse_rules(self, rules_tsv: str):
        parts = rules_tsv.splitlines()
        # @TODO make it

    def can_cast(self, tagkey: str) -> bool:
        if tagkey in ['wikidata']:
            return True
        return False

    def to_ttl(self, tagkey: str, tagvalue: str) -> str:
        # return f'    osmx:{tagkey} "{tagvalue}" ;'
        return f'    osmx:{tagkey} wikidata:{tagvalue} ;'


def osmrdf_node_xml2ttl(data_xml: str):

    osmx = OSMApiv06Xml(data_xml)
    osmnode = osmx.node()

    output = []
    output.extend(RDF_TURTLE_PREFIXES)
    output.append('')

    output.extend(osmnode.to_ttl())

    output.append('')
    # DEBUG: next 2 lines will print the XML node, commented
    # comment = "# " + "\n# ".join(data_xml.split("\n"))
    # output.append(comment)

    return "\n".join(output)


def osmrdf_relation_xml2ttl(data_xml: str):

    osmx = OSMApiv06Xml(data_xml)
    osmnode = osmx.node()

    output = []
    output.extend(RDF_TURTLE_PREFIXES)
    output.append('')

    output.extend(osmnode.to_ttl())

    output.append('')
    # DEBUG: next 2 lines will print the XML node, commented
    comment = "# " + "\n# ".join(data_xml.split("\n"))
    output.append(comment)

    return "\n".join(output)


def osmrdf_tagkey_encode(raw_tag: str) -> str:
    # @TODO improve-me
    # return raw_tag.replace(':', '%3A').replace(' ', '%20')
    return raw_tag.replace(' ', '%20')


def osmrdf_way_xml2ttl(data_xml: str):

    osmx = OSMApiv06Xml(data_xml)
    osmnode = osmx.node()

    # print(osmnode)
    # print(type(osmnode))
    # print(osmnode.to_ttl())
    # print(type(osmnode.to_ttl()))

    output = []
    output.extend(RDF_TURTLE_PREFIXES)
    output.append('')

    output.extend(osmnode.to_ttl())

    output.append('')
    # DEBUG: next 2 lines will print the XML node, commented
    # comment = "# " + "\n# ".join(data_xml.split("\n"))
    # output.append(comment)

    return "\n".join(output)


def osmrdf_xmldump2_ttl(xml_file_path, xml_filter: OSMElementFilter = None):
    """osmrdf_xmldump2_ttl _summary_

    @deprecated will be replaced later

    Args:
        xml_file_path (_type_): _description_
        xml_filter (OSMElementFilter, optional): _description_. Defaults to None.
    """
    # @TODO document-me

    from xml.etree import cElementTree as ET

    all_records = []

    print('\n'.join(RDF_TURTLE_PREFIXES))
    print('')

    count = 0
    xml_tags = []
    xml_nds = []
    xml_members = []
    for event, elem in ET.iterparse(xml_file_path, events=("start", "end")):

        # if elem not in ['node', 'way', 'relation']
        if elem.tag in ['bounds', 'osm']:
            continue

        # if elem.tag in ['nd', 'member', 'tag']:
        if elem.tag in ['nd', 'member']:
            # @FIXME way
            continue

        if event == 'start':
            _eltags = elem.findall("tag")
            if _eltags:
                for item in _eltags:
                    xml_tags.append((item.attrib['k'], item.attrib['v']))

            _elnds = elem.findall("nd")
            if _elnds:
                xml_nds = []
                for item in _elnds:
                    xml_nds.append(int(item.attrib['ref']))
            # xml_members = None
            _elmembers = elem.findall("member")
            if _elmembers:
                xml_members = []
                for item in _elmembers:
                    # @FIXME this is incomplete
                    _type = item.attrib['type']
                    _ref = int(item.attrib['ref'])
                    _role = item.attrib['role'] if 'role' in item.attrib else None
                    xml_members.append((_type, _ref, _role))

        if event == 'end':
            if elem.tag == 'tag':
                continue

            # print(elem, elem.attrib)

            child = elem

            # if xml_tags:
            #     print (xml_tags)
            #     sys.exit()

            el = OSMElement(
                child.tag,
                dict(child.attrib),
                xml_tags=xml_tags,
                xml_nds=xml_nds,
                xml_members=xml_members,
                xml_filter=xml_filter
            )
            xml_tags = []
            xml_nds = []
            xml_members = []
            if el.can_output():
                print('\n'.join(el.to_ttl()) + '\n')
                count += 1

        # if count > 10:
        #     break


def osmrdf_xmldump2_ttl_v2(
        xml_file_path,
        xml_filter: OSMElementFilter = None, retagger: str = None):
    # context = etree.iterparse(xml_file_path, events=('end',), tag='node')
    # context = etree.iterparse(xml_file_path, events=('end',), tag=('way'))

    print('\n'.join(RDF_TURTLE_PREFIXES))
    print('')

    # _tags = ('node', 'way', 'relation')
    _tags = ('way', 'relation')
    _rules = """+	<way>	*	is_in=BRA
-	<node>|<way>|<relation>	*	created_by=*
+	<way>|<relation>	*	shacl:lessThanOrEquals:maxspeed=120"""
    # retagger = OSMElementTagger(_rules)
    retagger = OSMElementTagger(retagger)
    tagcaster = OSMElementTagValueCast(None)

    # context = etree.iterparse(xml_file_path, events=('end',), tag=_tags)
    context = etree.iterparse(xml_file_path, events=('end',))

    count = 0
    xml_tags = []
    xml_nds = []
    xml_members = []
    for _event, elem in context:
        # if elem.tag in ['osm', 'bounds', 'nd', 'member', 'tag']:
        if elem.tag in ['osm', 'bounds', 'nd', 'member', 'tag', 'tagi']:
            continue

        _eltags = elem.findall("tag")
        if _eltags:
            for item in _eltags:
                xml_tags.append((item.attrib['k'], item.attrib['v']))
        xml_tags = retagger.retag(elem.tag, xml_tags)

        # "Implicit" tag "<tagi />"
        _elimplicittags = elem.findall("tagi")
        if _elimplicittags:
            for item in _elimplicittags:
                xml_tags.append((item.attrib['k'], item.attrib['v']))
        xml_tags = retagger.retag(elem.tag, xml_tags)

        _elnds = elem.findall("nd")
        if _elnds:
            xml_nds = []
            for item in _elnds:
                xml_nds.append(int(item.attrib['ref']))
        _elmembers = elem.findall("member")
        if _elmembers:
            xml_members = []
            for item in _elmembers:
                # @FIXME this is incomplete
                _type = item.attrib['type']
                _ref = int(item.attrib['ref'])
                _role = item.attrib['role'] if 'role' in item.attrib else None
                xml_members.append((_type, _ref, _role))

        el = OSMElement(
            elem.tag,
            dict(elem.attrib),
            xml_tags=xml_tags,
            xml_nds=xml_nds,
            xml_members=xml_members,
            xml_filter=xml_filter,
            tagcaster=tagcaster,
        )
        xml_tags = []
        xml_nds = []
        xml_members = []
        if el.can_output():
            print('\n'.join(el.to_ttl()) + '\n')
            count += 1

        elem.clear()
        while elem.getprevious() is not None:
            del elem.getparent()[0]


# @TODO after Protobuf, maybe try some alternative which could allow
#       search specific parts. See:
#       - https://wiki.openstreetmap.org/wiki/SQLite
#       - https://wiki.openstreetmap.org/wiki/SpatiaLite
#       - https://github.com/osmzoso/osm2sqlite
#

## TODO: extra code over https://github.com/EticaAI/openstreetmap-semantic-conventions-2023/blob/main/poc/osmapi2rdfproxy.py

OSM_API_DE_FACTO = os.getenv(
    'OSM_API_DE_FACTO', 'https://www.openstreetmap.org/api/0.6')
CACHE_DRIVER = os.getenv('CACHE_DRIVER', 'sqlite')
CACHE_TTL = os.getenv('CACHE_TTL', '3600')  # 1 hour

# @see https://requests-cache.readthedocs.io/en/stable/
requests_cache.install_cache(
    'osmapi_cache',
    # /tmp OpenFaaS allow /tmp be writtable even in read-only mode
    # However, is not granted that changes will persist or shared
    db_path= '/tmp/osmapi_cache.sqlite',
    backend=CACHE_DRIVER,
    expire_after=CACHE_TTL,
    allowable_codes=[200, 400, 404, 500]
)

def handle(event, context):

    if not event.path.startswith(('/node/', '/way/', '/relation/')):
        return {
            "statusCode": 404,
            "headers": {
                'content-type': 'application/json'
            },
            "body": {
                'error': 'Not found.',
                'examples': ["/node/1", "/way/100", "/relation/10000"]
            }
        }

    content = requests.get(
        OSM_API_DE_FACTO + event.path)

    body_text = content.text
    content_type = content.headers['Content-Type']

    if content.status_code == 200:
        if event.path.startswith('/node'):
            content_type = 'text/turtle'
            body_text = osmrdf_node_xml2ttl(body_text)

        elif event.path.startswith('/relation'):
            content_type = 'text/turtle'
            body_text = osmrdf_relation_xml2ttl(body_text)

        elif event.path.startswith('/way'):
            content_type = 'text/turtle'
            body_text = osmrdf_way_xml2ttl(body_text)

    return {
        "statusCode": content.status_code,
        "headers": {
            'content-type': content_type
        },
        "body": body_text
    }
