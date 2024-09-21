# Copyright (C) 2013-2018  Vincent Pelletier <plr.vincent@gmail.com>
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301  USA
"""Pythonified linux asm-generic/ioctl.h.

Produce IOCTL command numbers from their individual components, simplifying
C header conversion to python (keeping magic constants and differences to
C code to a minimum).

Common parameter meanings:
    type (8-bits unsigned integer)
        Driver-imposed ioctl number.
    nr (8-bits unsigned integer)
        Driver-imposed ioctl function number.

"type" parameters expect ctypes-based types (ctypes.Structure subclasses, ...).

https://github.com/vpelletier/python-ioctl-opt
Licensed under GPL 2.0
"""
import array
import ctypes
import struct

_IOC_NRBITS = 8
_IOC_TYPEBITS = 8
_IOC_SIZEBITS = 14
_IOC_DIRBITS = 2

_IOC_NRMASK = (1 << _IOC_NRBITS) - 1
_IOC_TYPEMASK = (1 << _IOC_TYPEBITS) - 1
_IOC_SIZEMASK = (1 << _IOC_SIZEBITS) - 1
_IOC_DIRMASK = (1 << _IOC_DIRBITS) - 1

_IOC_NRSHIFT = 0
_IOC_TYPESHIFT = _IOC_NRSHIFT + _IOC_NRBITS
_IOC_SIZESHIFT = _IOC_TYPESHIFT + _IOC_TYPEBITS
_IOC_DIRSHIFT = _IOC_SIZESHIFT + _IOC_SIZEBITS

IOC_NONE = 0
IOC_WRITE = 1
IOC_READ = 2

def IOC(dir, type, nr, size):
    """
    dir
        One of IOC_NONE, IOC_WRITE, IOC_READ, or IOC_READ|IOC_WRITE.
        Direction is from the application's point of view, not kernel's.
    size (14-bits unsigned integer)
        Size of the buffer passed to ioctl's "arg" argument.
    """
    assert dir <= _IOC_DIRMASK, dir
    assert type <= _IOC_TYPEMASK, type
    assert nr <= _IOC_NRMASK, nr
    assert size <= _IOC_SIZEMASK, size
    return (dir << _IOC_DIRSHIFT) | (type << _IOC_TYPESHIFT) | (nr << _IOC_NRSHIFT) | (size << _IOC_SIZESHIFT)

def IOC_TYPECHECK(t):
    """
    Returns the size of given type, and check its suitability for use in an
    ioctl command number.
    """
    if isinstance(t, (memoryview, bytearray)):
        size = len(t)
    elif isinstance(t, struct.Struct):
        size = t.size
    elif isinstance(t, array.array):
        size = t.itemsize * len(t)
    else:
        size = ctypes.sizeof(t)
    assert size <= _IOC_SIZEMASK, size
    return size

def IO(type, nr):
    """
    An ioctl with no parameters.
    """
    return IOC(IOC_NONE, type, nr, 0)

def IOR(type, nr, size):
    """
    An ioctl with read parameters.

    size (ctype type or instance, memoryview, bytearray, struct.Struct, or array.array)
        Type/structure of the argument passed to ioctl's "arg" argument.
    """
    return IOC(IOC_READ, type, nr, IOC_TYPECHECK(size))

def IOW(type, nr, size):
    """
    An ioctl with write parameters.

    size (ctype type or instance, memoryview, bytearray, struct.Struct, or array.array)
        Type/structure of the argument passed to ioctl's "arg" argument.
    """
    return IOC(IOC_WRITE, type, nr, IOC_TYPECHECK(size))

def IOWR(type, nr, size):
    """
    An ioctl with both read an writes parameters.

    size (ctype type or instance, memoryview, bytearray, struct.Struct, or array.array)
        Type/structure of the argument passed to ioctl's "arg" argument.
    """
    return IOC(IOC_READ | IOC_WRITE, type, nr, IOC_TYPECHECK(size))

def IOC_DIR(nr):
    """
    Extract direction from an ioctl command number.
    """
    return (nr >> _IOC_DIRSHIFT) & _IOC_DIRMASK

def IOC_TYPE(nr):
    """
    Extract type from an ioctl command number.
    """
    return (nr >> _IOC_TYPESHIFT) & _IOC_TYPEMASK

def IOC_NR(nr):
    """
    Extract nr from an ioctl command number.
    """
    return (nr >> _IOC_NRSHIFT) & _IOC_NRMASK

def IOC_SIZE(nr):
    """
    Extract size from an ioctl command number.
    """
    return (nr >> _IOC_SIZESHIFT) & _IOC_SIZEMASK

IOC_IN = IOC_WRITE << _IOC_DIRSHIFT
IOC_OUT = IOC_READ << _IOC_DIRSHIFT
IOC_INOUT = (IOC_WRITE | IOC_READ) << _IOC_DIRSHIFT
IOCSIZE_MASK = _IOC_SIZEMASK << _IOC_SIZESHIFT
IOCSIZE_SHIFT = _IOC_SIZESHIFT

if __name__ == '__main__':
    print('Sanity checks...')
    # hid.h
    HID_MAX_DESCRIPTOR_SIZE = 4096

    # hidraw.h
    class hidraw_report_descriptor(ctypes.Structure):
        _fields_ = [
            ('size', ctypes.c_uint),
            ('value', ctypes.c_ubyte * HID_MAX_DESCRIPTOR_SIZE),
        ]

    class hidraw_devinfo(ctypes.Structure):
        _fields_ = [
            ('bustype', ctypes.c_uint),
            ('vendor', ctypes.c_short),
            ('product', ctypes.c_short),
        ]

    HIDIOCGRDESCSIZE = IOR(ord('H'), 0x01, ctypes.c_int)
    HIDIOCGRDESC = IOR(ord('H'), 0x02, hidraw_report_descriptor)
    HIDIOCGRAWINFO = IOR(ord('H'), 0x03, hidraw_devinfo)
    HIDIOCGRAWNAME = lambda len: IOC(IOC_READ, ord('H'), 0x04, len)
    HIDIOCGRAWPHYS = lambda len: IOC(IOC_READ, ord('H'), 0x05, len)
    HIDIOCSFEATURE = lambda len: IOC(IOC_WRITE|IOC_READ, ord('H'), 0x06, len)
    HIDIOCGFEATURE = lambda len: IOC(IOC_WRITE|IOC_READ, ord('H'), 0x07, len)
    HIDIOCGRAWNAME(0)
    HIDIOCGRAWPHYS(1)
    HIDIOCGRAWPHYS(_IOC_SIZEMASK)
    HIDIOCGFEATURE(_IOC_SIZEMASK)
