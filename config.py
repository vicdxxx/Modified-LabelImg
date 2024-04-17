import numpy as n
import pprint
import cv2
import numpy as np
import pprint
import sys
import os
file_dir = os.path.dirname(__file__)
import pprint
import numpy as np

class AttrDict():
    """ Avoid accidental creation of new hierarchies. """
    _freezed = False
    def __getattr__(self, name):
        if self._freezed:
            raise AttributeError(name)
        ret = AttrDict()
        setattr(self, name, ret)
        return ret

    def __setattr__(self, name, value):
        if self._freezed and name not in self.__dict__:
            raise AttributeError(
                "Config was freezed! Unknown config_replenish: {}".format(name))
        super().__setattr__(name, value)

    def __str__(self):
        return pprint.pformat(self.to_dict(), indent=1)

    __repr__ = __str__

    def to_dict(self):
        """Convert to a nested dict. """
        return {
            k: v.to_dict() if isinstance(v, AttrDict) else v
            for k, v in self.__dict__.items() if not k.startswith('_')
        }

    def update_args(self, args):
        """Update from command line args. """
        for cfg in args:
            keys, v = cfg.split('=', maxsplit=1)
            keylist = keys.split('.')

            dic = self
            for i, k in enumerate(keylist[:-1]):
                assert k in dir(
                    dic), "Unknown config_replenish key: {}".format(keys)
                dic = getattr(dic, k)
            key = keylist[-1]

            oldv = getattr(dic, key)
            if not isinstance(oldv, str):
                v = eval(v)
            setattr(dic, key, v)

    def freeze(self, freezed=True):
        self._freezed = freezed
        for v in self.__dict__.values():
            if isinstance(v, AttrDict):
                v.freeze(freezed)

    # avoid silent bugs
    def __eq__(self, other):
        if isinstance(other,  self.__class__):
            return self.__dict__ == other.__dict__
        else:
            return False

    def __ne__(self, other):
        if isinstance(other,  self.__class__):
            return self.__dict__ != other.__dict__
        else:
            return True


config = AttrDict()
_C = config
_C.DEBUG = False
_C.INCLUDE_CHINSES = False

# exif
#from exif import Image as exif_Image

# add tracker for image sequence situation
# reserveAnnotation = action("reserveAnnotation", self.reserveAnnotation,
#                        'v', 'new', "reserveAnnotation")
# self.is_reserve_annotation
# self.loadPascalXMLByFilename(xmlPath)
#self.imageData = read(unicodeFilePath, None)
#image = QImage.fromData(self.imageData)
# self.reserveAnnotationTracker

_C.show_label = True

# for 1500x2000 or above
# 8
#_C.point_size = 7
#_C.scale = 1.0
# 2/3/4
#_C.pen_width = 4
# 16/100
#_C.font_point_size = 150
#_C.show_label_margin = 10

# for 1000x1900 or above
# 7
_C.point_size = 3
_C.scale = 1.0
# 2
_C.pen_width = 3
# 30
# 10
_C.font_point_size = 20
# 10
_C.show_label_margin = 5


# #for 3000x4000 or above
#_C.point_size = 3
#_C.scale = 1.0
#_C.pen_width = 3
#_C.font_point_size = 40
##_C.font_point_size = 50
#_C.show_label_margin = 10
