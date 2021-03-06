#!/usr/bin/env python
#
#This file is part of Cosmonium.
#
#Copyright (C) 2018-2019 Laurent Deru.
#
#Cosmonium is free software: you can redistribute it and/or modify
#it under the terms of the GNU General Public License as published by
#the Free Software Foundation, either version 3 of the License, or
#(at your option) any later version.
#
#Cosmonium is distributed in the hope that it will be useful,
#but WITHOUT ANY WARRANTY; without even the implied warranty of
#MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#GNU General Public License for more details.
#
#You should have received a copy of the GNU General Public License
#along with Cosmonium.  If not, see <https://www.gnu.org/licenses/>.
#

# This demo is heavily based on the Ralph example of Panda3D
# Author: Ryan Myers
# Models: Jeff Styers, Reagan Heller
#

from __future__ import print_function

import sys

# Add third-party/ directory to import path to be able to load the external libraries
sys.path.insert(0, 'third-party')
# CEFPanda and glTF modules aree not at top level
sys.path.insert(0, 'third-party/cefpanda')
sys.path.insert(0, 'third-party/gltf')

from panda3d.core import AmbientLight, DirectionalLight, LPoint3, LVector3, LQuaternion, LColor
from panda3d.core import LPoint3d, LQuaterniond
from panda3d.core import PandaNode, NodePath
from direct.actor.Actor import Actor

from cosmonium.heightmapshaders import HeightmapDataSource, DisplacementVertexControl
from cosmonium.procedural.shaders import TextureDictionaryDataSource
from cosmonium.procedural.shaders import DetailMap
from cosmonium.procedural.water import WaterNode
from cosmonium.appearances import ModelAppearance
from cosmonium.shaders import BasicShader, Fog, ConstantTessellationControl, ShaderShadowMap
from cosmonium.shapes import InstanceShape, CompositeShapeObject
from cosmonium.surfaces import HeightmapSurface
from cosmonium.tiles import Tile, TiledShape, GpuPatchTerrainLayer, MeshTerrainLayer
from cosmonium.heightmap import PatchedHeightmap
from cosmonium.procedural.shaderheightmap import ShaderHeightmapPatchFactory
from cosmonium.patchedshapes import VertexSizeMaxDistancePatchLodControl
from cosmonium.shadows import ShadowMap
from cosmonium.parsers.yamlparser import YamlModuleParser
from cosmonium.parsers.noiseparser import NoiseYamlParser
from cosmonium.parsers.populatorsparser import PopulatorYamlParser
from cosmonium.parsers.textureparser import TextureControlYamlParser, HeightColorControlYamlParser, TextureDictionaryYamlParser
from cosmonium.ui.splash import NoSplash
from cosmonium import settings

from math import pow, pi, sqrt
import argparse

from cosmonium.cosmonium import CosmoniumBase
from cosmonium.camera import CameraBase
from cosmonium.nav import NavBase
from cosmonium.astro.frame import AbsoluteReferenceFrame
from cosmonium.parsers.heightmapsparser import InterpolatorYamlParser

class TileFactory(object):
    def __init__(self, heightmap, tile_density, size, height_scale, has_water, water):
        self.heightmap = heightmap
        self.tile_density = tile_density
        self.size = size
        self.height_scale = height_scale
        self.has_water = has_water
        self.water = water

    def create_patch(self, parent, lod, x, y):
        min_height = -self.height_scale
        max_height = self.height_scale
        if parent is not None:
            heightmap_patch = self.heightmap.get_heightmap(parent)
            if heightmap_patch is not None:
                min_height = heightmap_patch.min_height * self.height_scale
                max_height = heightmap_patch.max_height * self.height_scale
        patch = Tile(parent, lod, x, y, self.tile_density, self.size, min_height, max_height)
        #print("Create tile", patch.lod, patch.x, patch.y, patch.size, patch.scale, patch.flat_coord)
        if settings.hardware_tessellation:
            terrain_layer = GpuPatchTerrainLayer()
        else:
            terrain_layer = MeshTerrainLayer()
        patch.add_layer(terrain_layer)
        if self.has_water:
            patch.add_layer(WaterLayer(self.water))
        return patch

    def split_patch(self, parent):
        lod = parent.lod + 1
        delta = parent.half_size
        x = parent.x
        y = parent.y
        self.create_patch(parent, lod, x, y)
        self.create_patch(parent, lod, x + delta, y)
        self.create_patch(parent, lod, x + delta, y + delta)
        self.create_patch(parent, lod, x, y + delta)
        parent.children_bb = []
        parent.children_normal = []
        parent.children_offset = []
        for child in parent.children:
            parent.children_bb.append(child.bounds.make_copy())
            parent.children_normal.append(None)
            parent.children_offset.append(None)
            child.owner = parent.owner

    def merge_patch(self, patch):
        pass

class WaterLayer(object):
    def __init__(self, config):
        self.config = config
        self.water = None

    def check_settings(self):
        if self.water is not None:
            if self.config.visible:
                self.water.create_instance()
            else:
                self.water.remove_instance()

    def create_instance(self, patch):
        self.water = WaterNode(-0.5, -0.5, 0.5, 0.5, self.config.level, self.config.scale, patch)
        if self.config.visible:
            self.water.create_instance()

    def update_instance(self, patch):
        pass

    def remove_instance(self):
        if self.water is not None:
            self.water.remove_instance()
            self.water = None

class WaterConfig():
    def __init__(self, level, visible, scale):
        self.level = level
        self.visible = visible
        self.scale = scale

class RalphConfigParser(YamlModuleParser):
    def decode(self, data):
        biome = data.get('biome', None)
        control = data.get('control', None)
        appearance = data.get('appearance', None)
        water = data.get('water', None)
        fog = data.get('fog', None)

        terrain = data.get('terrain', {})
        self.tile_size = terrain.get("tile-size", 1024)
        self.tile_density = terrain.get('tile-density', 64)
        self.max_vertex_size = terrain.get('max-vertex-size', 128)
        self.max_lod = terrain.get('max-lod', 10)
        self.max_distance = terrain.get('max-distance', 1.001 * 1024 * sqrt(2))
        self.heightmap_size = terrain.get('heightmap-size', 512)
        self.biome_size = terrain.get('biome-size', 128)

        heightmap = data.get('heightmap', {})
        raw_height_scale = heightmap.get('max-height', 1.0)
        height_scale_units = heightmap.get('max-height-units', 1.0)
        scale_length = heightmap.get('scale-length', 2.0)
        noise = heightmap.get('noise')
        median = heightmap.get('median', True)
        self.height_scale = raw_height_scale * height_scale_units
        self.noise_scale = raw_height_scale
        #filtering = self.decode_filtering(heightmap.get('filter', 'none'))
        noise_parser = NoiseYamlParser(scale_length)
        self.heightmap = noise_parser.decode(noise)
        self.shadow_size = terrain.get('shadow-size', 16)
        self.shadow_box_length = terrain.get('shadow-depth', self.height_scale)
        self.interpolator = InterpolatorYamlParser.decode(heightmap.get('interpolator'))
        self.heightmap_max_lod = heightmap.get('max-lod', 100)

        layers = data.get('layers', [])
        self.layers = []
        for layer in layers:
            self.layers.append(PopulatorYamlParser.decode(layer))

        if biome is not None:
            self.biome = noise_parser.decode(biome)
        else:
            self.biome = None

        if appearance is not None:
            appearance_parser = TextureDictionaryYamlParser()
            self.appearance = appearance_parser.decode(appearance)
        else:
            self.appearance = None

        if control is not None:
            control_parser = TextureControlYamlParser()
            (self.control, appearance_source) = control_parser.decode(control, self.appearance, self.height_scale)
        else:
            self.control = None

        if water is not None:
            level = water.get('level', 0)
            visible = water.get('visible', False)
            scale = 8.0 #* self.size / self.default_size
            self.water = WaterConfig(level, visible, scale)
        else:
            self.water = WaterConfig(0, False, 1.0)
        if fog is not None:
            self.fog_parameters = {}
            self.fog_parameters['fall_off'] = fog.get('falloff', 0.035)
            self.fog_parameters['density'] = fog.get('density', 20)
            self.fog_parameters['ground'] = fog.get('ground', -500)
        else:
            self.fog_parameters = None
        return True

class NodePathHolder(object):
    def __init__(self, instance):
        self.instance = instance

    def get_rel_position_to(self, position):
        return LPoint3d(*self.instance.get_pos(render))

class RalphCamera(CameraBase):
    def __init__(self, cam, lens):
        CameraBase.__init__(self, cam, lens)
        self.camera_global_pos = LPoint3d()
        self.camera_frame = AbsoluteReferenceFrame()

    def get_frame_camera_pos(self):
        return LPoint3d(*base.cam.get_pos())

    def set_frame_camera_pos(self, position):
        base.cam.set_pos(*position)

    def get_frame_camera_rot(self):
        return LQuaterniond(*base.cam.get_quat())

    def set_frame_camera_rot(self, rot):
        base.cam.set_quat(LQuaternion(*rot))

    def set_camera_pos(self, position):
        base.cam.set_pos(*position)

    def get_camera_pos(self):
        return LPoint3d(*base.cam.get_pos())

    def set_camera_rot(self, rot):
        base.cam.set_quat(LQuaternion(*rot))

    def get_camera_rot(self):
        return LQuaterniond(*base.cam.get_quat())

class FollowCam(object):
    def __init__(self, terrain, cam, target, floater):
        self.terrain = terrain
        self.cam = cam
        self.target = target
        self.floater = floater
        self.height = 2.0
        self.min_height = 1.0
        self.max_dist = 10.0
        self.min_dist = 5.0
        self.cam.setPos(self.target.getX(), self.target.getY() + self.max_dist, self.height)

    def set_limits(self, min_dist, max_dist):
        self.min_dist = min_dist
        self.max_dist = max_dist

    def set_height(self, height):
        self.height = max(height, self.min_height)

    def scale_height(self, scale):
        self.height = max(self.min_height, self.height * scale)

    def update(self):
        vec = self.target.getPos() - self.cam.getPos()
        vec.setZ(0)
        dist = vec.length()
        vec.normalize()
        if dist > self.max_dist:
            self.cam.setPos(self.cam.getPos() + vec * (dist - self.max_dist))
            dist = self.max_dist
        if dist < self.min_dist:
            self.cam.setPos(self.cam.getPos() - vec * (self.min_dist - dist))
            dist = self.min_dist

        # Keep the camera at min_height above the terrain,
        # or camera_height above target, whichever is greater.
        terrain_height = self.terrain.get_height(self.cam.getPos())
        target_height = self.target.get_z()
        if terrain_height + self.min_height < target_height + self.height:
            new_camera_height = target_height + self.height
        else:
            new_camera_height = terrain_height + self.min_height
        self.cam.setZ(new_camera_height)

        # The camera should look in ralph's direction,
        # but it should also try to stay horizontal, so look at
        # a floater which hovers above ralph's head.
        self.cam.lookAt(self.floater)

class RalphNav(NavBase):
    def __init__(self, ralph, target, cam, observer, sun, follow):
        NavBase.__init__(self)
        self.ralph = ralph
        self.target = target
        self.cam = cam
        self.observer = observer
        self.sun = sun
        self.follow = follow
        self.isMoving = False
        self.mouseSelectClick = False

    def register_events(self, event_ctrl):
        self.keyMap = {
            "left": 0, "right": 0, "forward": 0, "backward": 0,
            "cam-left": 0, "cam-right": 0, "cam-up": 0, "cam-down": 0,
            "sun-left": 0, "sun-right": 0,
            "turbo": 0}
        event_ctrl.accept("arrow_left", self.setKey, ["left", True])
        event_ctrl.accept("arrow_right", self.setKey, ["right", True])
        event_ctrl.accept("arrow_up", self.setKey, ["forward", True])
        event_ctrl.accept("arrow_down", self.setKey, ["backward", True])
        event_ctrl.accept("shift", self.setKey, ["turbo", True])
        event_ctrl.accept("a", self.setKey, ["cam-left", True], direct=True)
        event_ctrl.accept("s", self.setKey, ["cam-right", True], direct=True)
        event_ctrl.accept("u", self.setKey, ["cam-up", True], direct=True)
        event_ctrl.accept("u-up", self.setKey, ["cam-up", False])
        event_ctrl.accept("d", self.setKey, ["cam-down", True], direct=True)
        event_ctrl.accept("d-up", self.setKey, ["cam-down", False])
        event_ctrl.accept("o", self.setKey, ["sun-left", True], direct=True)
        event_ctrl.accept("o-up", self.setKey, ["sun-left", False])
        event_ctrl.accept("p", self.setKey, ["sun-right", True], direct=True)
        event_ctrl.accept("p-up", self.setKey, ["sun-right", False])
        event_ctrl.accept("arrow_left-up", self.setKey, ["left", False])
        event_ctrl.accept("arrow_right-up", self.setKey, ["right", False])
        event_ctrl.accept("arrow_up-up", self.setKey, ["forward", False])
        event_ctrl.accept("arrow_down-up", self.setKey, ["backward", False])
        event_ctrl.accept("shift-up", self.setKey, ["turbo", False])
        event_ctrl.accept("a-up", self.setKey, ["cam-left", False])
        event_ctrl.accept("s-up", self.setKey, ["cam-right", False])

        event_ctrl.accept("mouse1", self.OnSelectClick )
        event_ctrl.accept("mouse1-up", self.OnSelectRelease )

        if settings.invert_wheel:
            event_ctrl.accept("wheel_up", self.change_distance, [0.1])
            event_ctrl.accept("wheel_down", self.change_distance, [-0.1])
        else:
            event_ctrl.accept("wheel_up", self.change_distance, [-0.1])
            event_ctrl.accept("wheel_down", self.change_distance, [0.1])

    def remove_events(self, event_ctrl):
        NavBase.remove_events(self, event_ctrl)

    def OnSelectClick(self):
        if base.mouseWatcherNode.hasMouse():
            self.mouseSelectClick = True
            mpos = base.mouseWatcherNode.getMouse()
            self.startX = mpos.getX()
            self.startY = mpos.getY()
            self.dragAngleX = pi
            self.dragAngleY = pi
            self.create_drag_params(self.target)

    def OnSelectRelease(self):
        if base.mouseWatcherNode.hasMouse():
            mpos = base.mouseWatcherNode.getMouse()
            if self.startX == mpos.getX() and self.startY == mpos.getY():
                pass
        self.mouseSelectClick = False

    def change_distance(self, step):
        camvec = self.ralph.getPos() - self.cam.getPos()
        camdist = camvec.length()
        camvec /= camdist
        new_dist = max(5.0, camdist * (1.0 + step))
        new_pos = self.ralph.getPos() - camvec * new_dist
        self.follow.set_limits(new_dist / 2.0, new_dist)
        self.follow.set_height(new_pos.get_z() - self.ralph.get_z())
        self.cam.set_pos(new_pos)

    def update(self, dt):
        if self.mouseSelectClick and base.mouseWatcherNode.hasMouse():
            mpos = base.mouseWatcherNode.getMouse()
            deltaX = mpos.getX() - self.startX
            deltaY = mpos.getY() - self.startY
            z_angle = -deltaX * self.dragAngleX
            x_angle = deltaY * self.dragAngleY
            self.do_drag(z_angle, x_angle, move=True, rotate=False)
            camvec = self.ralph.getPos() - self.cam.getPos()
            camdist = camvec.length()
            self.follow.set_height(self.cam.get_z() - self.ralph.get_z())
            self.follow.set_limits(camdist / 2.0, camdist)
            return True

        if self.keyMap["cam-left"]:
            self.cam.setX(self.cam, -20 * dt)
        if self.keyMap["cam-right"]:
            self.cam.setX(self.cam, +20 * dt)
        if self.keyMap["cam-up"]:
            self.follow.scale_height(1 + 2 * dt)
        if self.keyMap["cam-down"]:
            self.follow.scale_height(1 - 2 * dt)

        if self.keyMap["sun-left"]:
            self.sun.set_light_angle(self.sun.light_angle + 30 * dt)
        if self.keyMap["sun-right"]:
            self.sun.set_light_angle(self.sun.light_angle - 30 * dt)

        delta = 25
        if self.keyMap["turbo"]:
            delta *= 10
        if self.keyMap["left"]:
            self.ralph.setH(self.ralph.getH() + 300 * dt)
        if self.keyMap["right"]:
            self.ralph.setH(self.ralph.getH() - 300 * dt)
        if self.keyMap["forward"]:
            self.ralph.setY(self.ralph, -delta * dt)
        if self.keyMap["backward"]:
            self.ralph.setY(self.ralph, delta * dt)

        if self.keyMap["forward"] or self.keyMap["backward"] or self.keyMap["left"] or self.keyMap["right"]:
            if self.isMoving is False:
                self.ralph.loop("run")
                self.isMoving = True
        else:
            if self.isMoving:
                self.ralph.stop()
                self.ralph.pose("walk", 5)
                self.isMoving = False
        return False

class RalphAppConfig:
    def __init__(self):
        self.test_start = False

class RoamingRalphDemo(CosmoniumBase):

    def get_local_position(self):
        return base.cam.get_pos()

    def create_terrain_appearance(self):
        self.terrain_appearance = self.ralph_config.appearance

    def create_terrain_heightmap(self):
        self.heightmap = PatchedHeightmap('heightmap',
                                          self.ralph_config.heightmap_size,
                                          self.ralph_config.height_scale,
                                          self.ralph_config.tile_size,
                                          self.ralph_config.tile_size,
                                          True,
                                          ShaderHeightmapPatchFactory(self.ralph_config.heightmap),
                                          self.ralph_config.interpolator,
                                          max_lod=self.ralph_config.heightmap_max_lod)
        #TODO: should be set using a method or in constructor
        self.heightmap.global_scale = 1.0 / self.ralph_config.noise_scale

    def create_terrain_biome(self):
        self.biome = PatchedHeightmap('biome',
                                      self.ralph_config.biome_size,
                                      1.0,
                                      self.ralph_config.tile_size,
                                      self.ralph_config.tile_size,
                                      False,
                                      ShaderHeightmapPatchFactory(self.ralph_config.biome))

    def create_terrain_shader(self):
#         control4 = HeightColorMap('colormap',
#                 [
#                  ColormapLayer(0.00, top=LRGBColor(0, 0.1, 0.24)),
#                  ColormapLayer(0.40, top=LRGBColor(0, 0.1, 0.24)),
#                  ColormapLayer(0.49, top=LRGBColor(0, 0.6, 0.6)),
#                  ColormapLayer(0.50, bottom=LRGBColor(0.9, 0.8, 0.6), top=LRGBColor(0.5, 0.4, 0.3)),
#                  ColormapLayer(0.80, top=LRGBColor(0.2, 0.3, 0.1)),
#                  ColormapLayer(0.90, top=LRGBColor(0.7, 0.6, 0.4)),
#                  ColormapLayer(1.00, bottom=LRGBColor(1, 1, 1), top=LRGBColor(1, 1, 1)),
#                 ])
        appearance = DetailMap(self.ralph_config.control, self.heightmap, create_normals=True)
        data_source = [HeightmapDataSource(self.heightmap),
                       HeightmapDataSource(self.biome, normals=False),
                       TextureDictionaryDataSource(self.terrain_appearance)]
        if settings.hardware_tessellation:
            tessellation_control = ConstantTessellationControl(invert_v=True)
        else:
            tessellation_control = None
        self.terrain_shader = BasicShader(appearance=appearance,
                                          tessellation_control=tessellation_control,
                                          vertex_control=DisplacementVertexControl(self.heightmap),
                                          data_source=data_source)
        self.terrain_shader.add_shadows(ShaderShadowMap('caster', self.shadow_caster))

    def create_tile(self, x, y):
        self.terrain_shape.add_root_patch(x, y)

    def create_terrain(self):
        self.create_terrain_heightmap()
        self.create_terrain_biome()
        self.tile_factory = TileFactory(self.heightmap, self.ralph_config.tile_density, self.ralph_config.tile_size, self.ralph_config.height_scale, self.has_water, self.water)
        self.terrain_shape = TiledShape(self.tile_factory,
                                        self.ralph_config.tile_size,
                                        VertexSizeMaxDistancePatchLodControl(self.ralph_config.max_distance,
                                                                             self.ralph_config.max_vertex_size,
                                                                             density=settings.patch_constant_density,
                                                                             max_lod=self.ralph_config.max_lod))
        self.create_terrain_appearance()
        self.create_terrain_shader()
        self.terrain_object = HeightmapSurface(
                               'surface',
                               0,
                               self.terrain_shape,
                               self.heightmap,
                               self.biome,
                               self.terrain_appearance,
                               self.terrain_shader,
                               self.ralph_config.tile_size,
                               clickable=False,
                               average=True)
        self.terrain = CompositeShapeObject()
        self.terrain.add_component(self.terrain_object)
        self.terrain_object.set_parent(self)
        self.terrain.set_owner(self)
        self.terrain.set_parent(self)

    def create_instance(self):
        self.terrain.create_instance()
        if self.has_water:
            WaterNode.create_cam()

    def toggle_water(self):
        if not self.has_water: return
        self.water.visible = not self.water.visible
        if self.water.visible:
            WaterNode.create_cam()
        else:
            WaterNode.remove_cam()
        self.terrain_shape.check_settings()

    def get_height(self, position):
        height = self.terrain_object.get_height(position)
        if self.has_water and self.water.visible and height < self.water.level:
            height = self.water.level
        return height

    #Used by populator
    def get_height_patch(self, patch, u, v):
        height = self.terrain_object.get_height_patch(patch, u, v)
        if self.has_water and self.water.visible and height < self.water.level:
            height = self.water.level
        return height

    def skybox_init(self):
        skynode = base.cam.attachNewNode('skybox')
        self.skybox = loader.loadModel('ralph-data/models/rgbCube')
        self.skybox.reparentTo(skynode)

        self.skybox.setTextureOff(1)
        self.skybox.setShaderOff(1)
        self.skybox.setTwoSided(True)
        # make big enough to cover whole terrain, else there'll be problems with the water reflections
        self.skybox.setScale(1.5 * self.ralph_config.tile_size)
        self.skybox.setBin('background', 1)
        self.skybox.setDepthWrite(False)
        self.skybox.setDepthTest(False)
        self.skybox.setLightOff(1)
        self.skybox.setShaderOff(1)
        self.skybox.setFogOff(1)

        #self.skybox.setColor(.55, .65, .95, 1.0)
        self.skybox_color = LColor(pow(0.5, 1/2.2), pow(0.6, 1/2.2), pow(0.7, 1/2.2), 1.0)
        self.sun_color = LColor(pow(1.0, 1/2.2), pow(0.9, 1/2.2), pow(0.7, 1/2.2), 1.0)
        self.skybox.setColor(self.skybox_color)

    def set_light_angle(self, angle):
        self.light_angle = angle
        self.light_quat.setFromAxisAngleRad(angle * pi / 180, LVector3.forward())
        self.light_dir = self.light_quat.xform(LVector3.up())
        cosA = self.light_dir.dot(LVector3.up())
        self.vector_to_star = self.light_dir
        if self.shadow_caster is not None:
            self.shadow_caster.set_direction(-self.light_dir)
        if self.directionalLight is not None:
            self.directionalLight.setDirection(-self.light_dir)
        if cosA >= 0:
            coef = sqrt(cosA)
            self.light_color = (1, coef, coef, 1)
            self.directionalLight.setColor(self.light_color)
            new_sky_color = self.skybox_color * cosA
            new_sky_color[3] = 1.0
            self.skybox.setColor(new_sky_color)
            if self.fog is not None:
                self.fog.fog_color = self.skybox_color * cosA
                self.fog.sun_color = self.sun_color * cosA
        else:
            self.light_color = (0, 0, 0, 1)
            self.directionalLight.setColor(self.light_color)
            self.skybox.setColor(self.light_color)
            if self.fog is not None:
                self.fog.fog_color = self.skybox_color * 0
                self.fog.sun_color = self.sun_color * 0
        self.terrain.update_shader()

    def set_ambient(self, ambient):
        settings.global_ambient = clamp(ambient, 0.0, 1.0)
        if settings.srgb:
            corrected_ambient = pow(settings.global_ambient, 2.2)
        else:
            corrected_ambient = settings.global_ambient
        settings.corrected_global_ambient = corrected_ambient
        print("Ambient light level:  %.2f" % settings.global_ambient)

    def incr_ambient(self, ambient_incr):
        self.set_ambient(settings.global_ambient + ambient_incr)

    def update(self):
        self.terrain.update_instance(None, None)

    def apply_instance(self, instance):
        pass

    def get_apparent_radius(self):
        return 0

    def get_min_radius(self):
        return 0

    def get_max_radius(self):
        return 0

    def get_name(self):
        return "terrain"

    def is_emissive(self):
        return False

    def toggle_lod_freeze(self):
        settings.debug_lod_freeze = not settings.debug_lod_freeze

    def toggle_split_merge_debug(self):
        settings.debug_lod_split_merge = not settings.debug_lod_split_merge

    def toggle_bb(self):
        settings.debug_lod_show_bb = not settings.debug_lod_show_bb
        self.trigger_check_settings = True

    def toggle_frustum(self):
        settings.debug_lod_frustum = not settings.debug_lod_frustum
        self.trigger_check_settings = True

    def __init__(self, args):
        self.app_config = RalphAppConfig()
        CosmoniumBase.__init__(self)

        settings.color_picking = False
        if args.config is not None:
            self.config_file = args.config
        else:
            self.config_file = 'ralph-data/ralph.yaml'
        self.splash = NoSplash()
        self.ralph_config = RalphConfigParser()
        if self.ralph_config.load_and_parse(self.config_file) is None:
            sys.exit(1)
        self.water = self.ralph_config.water

        self.has_water = True
        self.fullscreen = False
        self.shadow_caster = None
        self.light_angle = None
        self.light_dir = LVector3.up()
        self.vector_to_star = self.light_dir
        self.light_quat = LQuaternion()
        self.light_color = (1.0, 1.0, 1.0, 1.0)
        self.directionalLight = None

        self.observer = RalphCamera(self.cam, self.camLens)
        self.observer.init()

        self.distance_to_obs = 2.0 #Can not be 0 !
        self.height_under = 0.0
        self.scene_position = LVector3()
        self.scene_scale_factor = 1
        self.scene_rel_position = LVector3()
        self.scene_orientation = LQuaternion()
        self.model_body_center_offset = LVector3()
        self.world_body_center_offset = LVector3()
        self.context = self
        self.oid_color = 0
        self.oid_texture = None
        self.size = self.ralph_config.tile_size #TODO: Needed by populator

        #Size of an edge seen from 4 units above
        self.edge_apparent_size = (1.0 * self.ralph_config.tile_size / self.ralph_config.tile_density) / (4.0 * self.observer.pixel_size)
        print("Apparent size:", self.edge_apparent_size)

        self.win.setClearColor((135.0/255, 206.0/255, 235.0/255, 1))


        # Set up the environment
        #
        # Create some lighting
        self.vector_to_obs = base.cam.get_pos()
        self.vector_to_obs.normalize()
        if True:
            self.shadow_caster = ShadowMap(1024)
            self.shadow_caster.create()
            self.shadow_caster.set_lens(self.ralph_config.shadow_size, -self.ralph_config.shadow_box_length / 2.0, self.ralph_config.shadow_box_length / 2.0, -self.light_dir)
            self.shadow_caster.set_pos(self.light_dir * self.ralph_config.shadow_box_length / 2.0)
            self.shadow_caster.bias = 0.1
        else:
            self.shadow_caster = None

        self.ambientLight = AmbientLight("ambientLight")
        self.ambientLight.setColor((settings.global_ambient, settings.global_ambient, settings.global_ambient, 1))
        self.directionalLight = DirectionalLight("directionalLight")
        self.directionalLight.setDirection(-self.light_dir)
        self.directionalLight.setColor(self.light_color)
        self.directionalLight.setSpecularColor(self.light_color)
        render.setLight(render.attachNewNode(self.ambientLight))
        render.setLight(render.attachNewNode(self.directionalLight))

        render.setShaderAuto()
        base.setFrameRateMeter(True)

        self.create_terrain()
        for component in self.ralph_config.layers:
            self.terrain.add_component(component)
            self.terrain_shape.add_linked_object(component)

        if self.ralph_config.fog_parameters is not None:
            self.fog = Fog(**self.ralph_config.fog_parameters)
            self.terrain.add_after_effect(self.fog)
        else:
            self.fog = None
        self.surface = self.terrain_object

        self.create_instance()
        self.create_tile(0, 0)
        self.skybox_init()

        self.set_light_angle(45)

        # Create the main character, Ralph

        ralphStartPos = LPoint3()
        self.ralph = Actor("ralph-data/models/ralph",
                           {"run": "ralph-data/models/ralph-run",
                            "walk": "ralph-data/models/ralph-walk"})
        self.ralph.reparentTo(render)
        self.ralph.setScale(.2)
        self.ralph.setPos(ralphStartPos + (0, 0, 0.5))
        self.ralph_shape = InstanceShape(self.ralph)
        self.ralph_shape.parent = self
        self.ralph_shape.set_owner(self)
        self.ralph_shape.create_instance()
        self.ralph_appearance = ModelAppearance(self.ralph, vertex_color=True, material=False)
        self.ralph_shader = BasicShader()
        self.ralph_shader.add_shadows(ShaderShadowMap('caster', self.shadow_caster))
        self.ralph_appearance.bake()
        self.ralph_appearance.apply(self.ralph_shape, self.ralph_shader)
        self.ralph_shader.apply(self.ralph_shape, self.ralph_appearance)
        self.ralph_shader.update(self.ralph_shape, self.ralph_appearance)

        # Create a floater object, which floats 2 units above ralph.  We
        # use this as a target for the camera to look at.

        self.floater = NodePath(PandaNode("floater"))
        self.floater.reparentTo(self.ralph)
        self.floater.setZ(2.0)

        self.ralph_body = NodePathHolder(self.ralph)
        self.ralph_floater = NodePathHolder(self.floater)

        self.follow_cam = FollowCam(self, self.cam, self.ralph, self.floater)

        self.nav = RalphNav(self.ralph, self.ralph_floater, self.cam, self.observer, self, self.follow_cam)
        self.nav.register_events(self)

        self.accept("escape", sys.exit)
        self.accept("control-q", sys.exit)
        self.accept("w", self.toggle_water)
        self.accept("h", self.print_debug)
        self.accept("f2", self.connect_pstats)
        self.accept("f3", self.toggle_filled_wireframe)
        self.accept("shift-f3", self.toggle_wireframe)
        self.accept("f5", self.bufferViewer.toggleEnable)
        self.accept('f8', self.toggle_lod_freeze)
        self.accept("shift-f8", self.terrain_shape.dump_tree)
        self.accept('control-f8', self.toggle_split_merge_debug)
        self.accept('shift-f9', self.toggle_bb)
        self.accept('control-f9', self.toggle_frustum)
        self.accept("f10", self.save_screenshot)
        self.accept('alt-enter', self.toggle_fullscreen)
        self.accept('{', self.incr_ambient, [-0.05])
        self.accept('}', self.incr_ambient, [+0.05])

        taskMgr.add(self.move, "moveTask")

        # Set up the camera
        self.follow_cam.update()
        self.distance_to_obs = self.cam.get_z() - self.get_height(self.cam.getPos())
        render.set_shader_input("camera", self.cam.get_pos())

        self.terrain.update_instance(LPoint3d(*self.cam.getPos()), None)

    def move(self, task):
        dt = globalClock.getDt()

        if self.trigger_check_settings:
            self.terrain.check_settings()
            self.trigger_check_settings = False

        control = self.nav.update(dt)

        ralph_height = self.get_height(self.ralph.getPos())
        self.ralph.setZ(ralph_height)

        if not control:
            self.follow_cam.update()
        else:
            #TODO: Should have a FreeCam class for mouse orbit and this in update()
            self.cam.lookAt(self.floater)

        if self.shadow_caster is not None:
            vec = self.ralph.getPos() - self.cam.getPos()
            vec.set_z(0)
            dist = vec.length()
            vec.normalize()
            self.shadow_caster.set_pos(self.ralph.get_pos() - vec * dist + vec * self.ralph_config.shadow_size / 2)

        render.set_shader_input("camera", self.cam.get_pos())
        self.vector_to_obs = base.cam.get_pos()
        self.vector_to_obs.normalize()
        self.distance_to_obs = self.cam.get_z() - self.get_height(self.cam.getPos())
        self.scene_rel_position = -base.cam.get_pos()

        self.terrain.update_instance(LPoint3d(*self.cam.getPos()), None)
        self.ralph_shader.update(self.ralph_shape, self.ralph_appearance)
        return task.cont

    def print_debug(self):
        print("Height:", self.get_height(self.ralph.getPos()), self.terrain_object.get_height(self.ralph.getPos()))
        print("Ralph:", self.ralph.get_pos())
        print("Camera:", base.cam.get_pos(), self.follow_cam.height, self.distance_to_obs)

parser = argparse.ArgumentParser()
parser.add_argument("--config",
                    help="Path to the file with the configuration",
                    default=None)
if sys.platform == "darwin":
    #Ignore -psn_<app_id> from MacOS
    parser.add_argument('-p', help=argparse.SUPPRESS)
args = parser.parse_args()

demo = RoamingRalphDemo(args)
demo.run()
