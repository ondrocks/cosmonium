# -*- coding: utf-8 -*-
from __future__ import print_function
from __future__ import absolute_import

from ..astro.frame import J2000EclipticReferenceFrame, J2000EquatorialReferenceFrame, EquatorialReferenceFrame
from ..astro import units

from .yamlparser import YamlModuleParser

import re

hour_angle_regex= re.compile('^(\d+)\:(\d+)\'(\d+\.?\d*)\"$')
degree_angle_regex= re.compile(u'^([-+]?\d+)[d°](\d+)\'(\d+\.?\d*)\"$')

def hour_angle_decoder(text):
    if text is None: return None
    angle = None
    m = hour_angle_regex.search(text)
    if m is not None:
        hours = float(m.group(1))
        mins = float(m.group(2))
        secs = float(m.group(3))
        angle = units.hourMinSec(hours, mins, secs)
    return angle

def degree_angle_decoder(text):
    if text is None: return None
    angle = None
    m = degree_angle_regex.search(text)
    if m is not None:
        degrees = float(m.group(1))
        mins = float(m.group(2))
        secs = float(m.group(3))
        angle = units.degMinSec(degrees, mins, secs)
    return angle

class DistanceUnitsYamlParser(YamlModuleParser):
    translation = { 'km': units.Km,
                    'au': units.AU,
                    'ly': units.Ly,
                    'pc': units.Parsec,
                   }
    @classmethod
    def decode(self, data, default=None):
        if data is None:
            return default
        else:
            return DistanceUnitsYamlParser.translation.get(data.lower(), default)

class TimeUnitsYamlParser(YamlModuleParser):
    translation = { 'hour': units.Hour,
                    'day': units.Day,
                    'year': units.JYear,
                   }
    @classmethod
    def decode(self, data, default=None):
        if data is None:
            return default
        else:
            return TimeUnitsYamlParser.translation.get(data.lower(), default)

class AngleUnitsYamlParser(YamlModuleParser):
    translation = { 'deg': units.Deg,
                    'hour': units.HourAngle,
                    'rad': units.Rad
                   }
    @classmethod
    def decode(self, data, default=None):
        if data is None:
            return default
        else:
            return AngleUnitsYamlParser.translation.get(data.lower(), default)

class FrameYamlParser(YamlModuleParser):
    @classmethod
    def decode(self, data):
        name = data.lower()
        if name == 'j2000ecliptic':
            return J2000EclipticReferenceFrame()
        elif name == 'j2000equatorial':
            return J2000EquatorialReferenceFrame()
        elif name == 'equatorial':
            return EquatorialReferenceFrame()
        else:
            print("Unknown reference frame", data)
            return None
