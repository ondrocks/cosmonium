from __future__ import print_function
from __future__ import absolute_import

from panda3d.core import LVector3d

from ..universe import Universe
from ..galaxies import Galaxy
from ..celestia import config_parser
from ..astro.orbits import FixedPosition
from ..astro.rotations import FixedRotation
from ..astro import units
from ..dircontext import defaultDirContext
from .. import utils

import sys
import io

def names_list(name):
    return name.split(':')

def instanciate_body(universe, item_type, item_name, item_data):
    ra=None
    decl=None
    distance=None
    type=None
    radius=None
    axis=None
    angle=None
    abs_magnitude=None
    app_magnitude=None
    orbit=None
    axis = LVector3d.up()
    angle = 0.0
    names = names_list(item_name)
    for (key, value) in item_data.items():
        if key == 'RA':
            ra = value
        elif key == 'Dec':
            decl = value
        elif key == 'Distance':
            distance = value
        elif key == 'Type':
            type = value
        elif key == 'Radius':
            radius = value
        elif key == 'Axis':
            axis = LVector3d(*value)
        elif key == 'Angle':
            angle = value
        elif key == 'AbsMag':
            abs_magnitude = value
        elif key == 'AppMag':
            app_magnitude = value
        elif key == 'InfoURL':
            pass # = value
        else:
            print("Key of", item_type, key, "not supported")
    orbit = FixedPosition(right_asc=ra, right_asc_unit=units.HourAngle, declination=decl, distance=distance, distance_unit=units.Ly)
    rot=utils.LQuaternionromAxisAngle(axis, angle, units.Deg)
    rotation=FixedRotation(rot)
    if app_magnitude != None and distance != None:
        abs_magnitude = units.app_to_abs_mag(app_magnitude, distance)
    dso = Galaxy(names,
                abs_magnitude=abs_magnitude,
                radius=radius,
                orbit=orbit,
                rotation=rotation)
    return dso

def instanciate_item(universe, disposition, item_type, item_name, item_parent, item_alias, item_data):
    if disposition != 'Add':
        print("Disposition", disposition, "not supported")
        return
    if item_parent:
        print("Parent", item_parent, "not supported")        
    if item_type == 'Galaxy':
        body = instanciate_body(universe, item_type, item_name, item_data)
        universe.add_child_fast(body)
    else:
        print("Type", item_type, "not supported")
        return

def instanciate(items_list, universe):
    for item in items_list:
        instanciate_item(universe, *item)

def parse_file(filename, universe, context=defaultDirContext):
    filepath = context.find_data(filename)
    if filepath is not None:
        print("Loading", filepath)
        base.splash.set_text("Loading %s" % filepath)
        data = io.open(filepath, encoding='latin-1').read()
        items = config_parser.parse(data)
        if items is not None:
            instanciate(items, universe)
    else:
        print("File not found", filename)

def load(dsc, universe, context=defaultDirContext):
    if isinstance(dsc, list):
        for dsc in dsc:
            parse_file(dsc, universe, context)
    else:
        parse_file(dsc, universe, context)

if __name__ == '__main__':
    universe=Universe(None)
    if len(sys.argv) == 2:
        parse_file(sys.argv[1], universe)
