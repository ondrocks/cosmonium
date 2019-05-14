from __future__ import print_function

from panda3d.core import LPoint3d
from math import sqrt

class Octree(object):
    max_level = 200
    max_leaves = 25
    coef = sqrt(3)
    check_threshold = True
    nb_cells = 0
    nb_leaves = 0
    def __init__(self, level, center, width, threshold, index = -1):
        self.level = level
        self.width = width
        self.half_width = width / 2.0
        self.radius = self.width * self.coef
        self.center = center
        self.threshold = threshold
        self.child_threshold = threshold + 0.5
        self.index = index
        self.has_children = False
        self.children = [None, None, None, None, None, None, None, None]
        self.leaves = []
        self.max_magnitude = 99.0
        self.update_id = 0
        Octree.nb_cells += 1

    def add_in_child(self, obj, position, magnitude):
        index = 0
        if position.x >= self.center.x: index |= 1
        if position.y >= self.center.y: index |= 2
        if position.z >= self.center.z: index |= 4
        if self.children[index] is None:
            child_center = LPoint3d(self.center)
            if (index & 1) != 0:
                child_center.x += self.half_width
            else:
                child_center.x -= self.half_width
            if (index & 2) != 0:
                child_center.y += self.half_width
            else:
                child_center.y -= self.half_width
            if (index & 4) != 0:
                child_center.z += self.half_width
            else:
                child_center.z -= self.half_width
            child = Octree(self.level + 1, child_center, self.half_width, self.child_threshold, index)
            self.children[index] = child
            Octree.nb_cells += 1
        self.children[index].add(obj, position, magnitude)

    def add(self, obj, position, magnitude):
        self.nb_leaves += 1
        if magnitude < self.max_magnitude:
            self.max_magnitude = magnitude
        if not self.has_children or (self.check_threshold and magnitude < self.threshold) or (position - self.center).length() < 1.0:
            self.leaves.append(obj)
        else:
            self.add_in_child(obj, position, magnitude)
        if self.level < self.max_level and len(self.leaves) >= self.max_leaves and not self.has_children:
            self.split()

    def split(self):
        new_leaves = []
        for leaf in self.leaves:
            if (self.check_threshold and leaf.get_abs_magnitude() < self.threshold) or (leaf.get_global_position() - self.center).length() < 1.0:
                new_leaves.append(leaf)
            else:
                self.add_in_child(leaf, leaf.get_global_position(), leaf.get_abs_magnitude())
        self.leaves = new_leaves
        self.has_children = True

    def print(self):
        if len(self.leaves) > 0:
            print(' ' * self.level, self.level, self.index, self.width, self.threshold, self.center, self.has_children)
            print(' ' * self.level, '->', self.max_magnitude, ":", ', '.join(map(lambda x: x.get_name(), self.leaves)))
        for i in range(8):
            if self.children[i] is not None:
                self.children[i].print()

    def print_stats(self):
        print("Nb cells:", self.nb_cells)
        print("Nb leaves:", self.nb_leaves)