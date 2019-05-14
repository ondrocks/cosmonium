from __future__ import print_function
from __future__ import absolute_import

from ..procedural.shadernoise import NoiseConst, NoiseMap
from ..astro import units

from .yamlparser import YamlParser
from .utilsparser import DistanceUnitsYamlParser

class NoiseYamlParser(YamlParser):
    parsers = {}

    def __init__(self, height_scale=1.0, length_scale=1.0):
        self.height_scale = height_scale
        self.length_scale = length_scale

    @classmethod
    def register_noise_parser(cls, name, parser):
        cls.parsers[name] = parser

    def add_scale(self, noise, data):
        if not isinstance(data, dict): return noise
        min_value = data.get('min', None)
        max_value = data.get('max', None)
        if min_value is None and max_value is None:
            scale = data.get('scale', None)
            offset = data.get('offset', None)
            if scale is None and offset is None:
                return noise
            if scale is not None:
                scale *= self.height_scale
            else:
                scale = 1.0
            if offset is None:
                offset = 0.0
            min_value = -scale + offset
            max_value = scale + offset
        else:
            if min_value is not None:
                min_value *= self.height_scale
            else:
                min_value = -1.0
            if max_value is not None:
                max_value *= self.height_scale
            else:
                max_value = 1.0
        return NoiseMap(noise, min_value, max_value)

    def decode_noise(self, func, parameters):
        result = None
        if func in self.parsers:
            result = self.parsers[func](self, parameters, self.height_scale, self.length_scale)
        else:
            print("Unknown noise function", func)
        if result is not None:
            result = self.add_scale(result, parameters)
        return result

    def decode_noise_dict(self, data):
        if isinstance(data, (float, int)):
            return NoiseConst(data)
        (func, parameters) = self.get_type_and_data(data)
        return self.decode_noise(func, parameters)

    def decode_noise_list(self, data):
        noises = []
        for noise in data:
            noises.append(self.decode_noise_dict(noise))
        return noises

    def decode(self, data):
        aliases = data.get('aliases', {})
        for (alias, func) in aliases.items():
            parser = self.parsers.get(func, None)
            if parser is not None:
                self.register_noise_parser(alias, parser)
            else:
                print("Function", func, "unknown")
        noise = data.get('noise')
        return self.decode_noise_dict(noise)

from ..procedural.shadernoise import NoiseSourceScale, NoiseOffset, NoiseClamp
from ..procedural.shadernoise import NoiseAdd, NoiseSub, NoiseMul, NoisePow, NoiseThreshold
from ..procedural.shadernoise import RidgedNoise, TurbulenceNoise, AbsNoise, FbmNoise
from ..procedural.shadernoise import NoiseWarp, Noise1D
from ..procedural.shadernoise import GpuNoiseLibPerlin3D, SteGuPerlin3D, QuilezPerlin3D

def create_add_noise(parser, data, height_scale, length_scale):
    noises = parser.decode_noise_list(data)
    return NoiseAdd(noises)

def create_sub_noise(parser, data, height_scale, length_scale):
    a = parser.decode_noise_dict(data[0])
    b = parser.decode_noise_dict(data[1])
    return NoiseSub(a, b)

def create_mul_noise(parser, data, height_scale, length_scale):
    noises = parser.decode_noise_list(data)
    return NoiseMul(noises)

def create_pow_noise(parser, data, height_scale, length_scale):
    a = parser.decode_noise_dict(data[0])
    b = parser.decode_noise_dict(data[1])
    return NoisePow(a, b)

def create_threshold_noise(parser, data, height_scale, length_scale):
    a = parser.decode_noise_dict(data[0])
    b = parser.decode_noise_dict(data[1])
    return NoiseThreshold(a, b)

def create_clamp_noise(parser, data, height_scale, length_scale):
    noise = parser.decode_noise_dict(data.get('noise'))
    min_value = data.get('min', 0.0)
    max_value = data.get('min', 1.0)
    return NoiseClamp(noise, min_value, max_value)

def create_gpunoise_perlin_noise(parser, data, height_scale, length_scale):
    return GpuNoiseLibPerlin3D()

def create_stegu_perlin_noise(parser, data, height_scale, length_scale):
    return SteGuPerlin3D()

def create_iq_perlin_noise(parser, data, height_scale, length_scale):
    return QuilezPerlin3D()

def create_scale_noise(parser, data, height_scale, length_scale):
    noise = parser.decode_noise_dict(data.get('noise'))
    scale = data.get('scale', 1.0)
    #TODO: rename this parameter to src-scale ?
    data['scale'] = None
    return NoiseSourceScale(noise, scale)

def create_offset_noise(parser, data, height_scale, length_scale):
    noise = parser.decode_noise_dict(data.get('noise'))
    offset = data.get('offset', 0.0)
    #TODO: rename this parameter to src-offset ?
    data['offset'] = None
    return NoiseOffset(noise, offset)

def create_ridged_noise(parser, data, height_scale, length_scale):
    noise = parser.decode_noise_dict(data)
    return RidgedNoise(noise)

def create_turbulence_noise(parser, data, height_scale, length_scale):
    noise = parser.decode_noise_dict(data)
    return TurbulenceNoise(noise)

def create_abs_noise(parser, data, height_scale, length_scale):
    noise = parser.decode_noise_dict(data)
    return AbsNoise(noise)

def create_1d_noise(parser, data, height_scale, length_scale):
    noise = parser.decode_noise_dict(data.get('noise'))
    axis = data.get('axis', "z")
    return Noise1D(noise, axis)

def create_fbm_noise(parser, data, height_scale, length_scale):
    noise = parser.decode_noise_dict(data.get('noise'))
    octaves = data.get('octaves', 8)
    frequency = data.get('frequency', None)
    if frequency is None:
        length = data.get('length', length_scale)
        length_units = DistanceUnitsYamlParser.decode(data.get('length-units'), units.Km)
        if length is not None:
            length *= length_units
            frequency = length_scale / (length * 4)
        else:
            frequency = 1.0
    lacunarity = data.get('lacunarity', 2.0)
    geometric = data.get('geometric', True)
    h = data.get('h', 0.25)
    gain = data.get('gain', 0.5)

    return FbmNoise(noise, octaves, frequency, lacunarity, geometric, h, gain)

def create_warp_noise(parser, data, height_scale, length_scale):
    main = parser.decode_noise_dict(data.get('noise'))
    warp = parser.decode_noise_dict(data.get('warp'))
    scale = float(data.get('strength', 4.0))
    return NoiseWarp(main, warp, scale)

NoiseYamlParser.register_noise_parser('scale', create_scale_noise)
NoiseYamlParser.register_noise_parser('offset', create_offset_noise)

NoiseYamlParser.register_noise_parser('add', create_add_noise)
NoiseYamlParser.register_noise_parser('sub', create_sub_noise)
NoiseYamlParser.register_noise_parser('mul', create_mul_noise)
NoiseYamlParser.register_noise_parser('pow', create_pow_noise)
NoiseYamlParser.register_noise_parser('threshold', create_threshold_noise)
NoiseYamlParser.register_noise_parser('clamp', create_clamp_noise)
NoiseYamlParser.register_noise_parser('abs', create_abs_noise)
NoiseYamlParser.register_noise_parser('1d', create_1d_noise)

NoiseYamlParser.register_noise_parser('ridged', create_ridged_noise)
NoiseYamlParser.register_noise_parser('turbulence', create_turbulence_noise)
NoiseYamlParser.register_noise_parser('fbm', create_fbm_noise)
NoiseYamlParser.register_noise_parser('warp', create_warp_noise)

NoiseYamlParser.register_noise_parser('gpunoise:perlin', create_gpunoise_perlin_noise)
NoiseYamlParser.register_noise_parser('stegu:perlin', create_stegu_perlin_noise)
NoiseYamlParser.register_noise_parser('iq:perlin', create_iq_perlin_noise)
