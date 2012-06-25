################################################################################
## ozi2geotiff ( convert maps from Ozi Explorer format to GeoTiff )
##
## Copyright (C) 2008 Andrew Vagin
##
## This program is free software; you can redistribute it and/or modify
## it under the terms of the GNU General Public License as published by
## the Free Software Foundation; either version 2 of the License, or
## (at your option) any later version.
## This program is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU General Public License for more details.
##
## You should have received a copy of the GNU General Public License
## along with this program; if not, write to the Free Software
## Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA
##
## Andrew Vagin <avagin@gmail.com>
##
################################################################################

from logging import critical, error, warn, info, debug
import os, logging, ntpath
from optparse import OptionParser
from subprocess import Popen, PIPE
import math
import tempfile
DEG_TO_RAD = math.pi / 180.0

def degmin_to_deg(s, d, m):
	deg = abs(d) + m / 60.0;
	if s:
		deg = -deg
	return deg

def gdalwarp(infile, outfile, order = 0):
	info("execute gdalwarp")
	#TODO investigate -order and -tps
	args = ["gdalwarp", "-tps"]
	args.extend(["-dstnodata", "255"])
	args.extend([infile, outfile])
	debug(args)
	gdalwarp = Popen(args)
	ret = gdalwarp.wait()
	if ret:
		raise Exception("gdalwarp failed: return %d" % ret)

def gdal_translate2(infile, outfile):
	info("execute gdal_translate")
	args = ["gdal_translate"]
	args += ["-co", "tiled=yes"]
	args += ["-co", "blockxsize=256"]
	args += ["-co", "blockysize=256"]
	args += ["-co", "compress=deflate"]
	args += ["-co", "predictor=1"]
	args += [infile, outfile]
	debug(args)
	gdal_translate = Popen(args)
	ret = gdal_translate.wait()
	if ret:
		raise Exception("gdal_translate failed: return %d" % ret)

def convert_ozi_map(mapfile, imgfile, outfile):
	# defule projection.
	# TODO: get projection from ozi files
	projection = "+proj=merc +ellps=WGS84 +datum=WGS84 +no_defs"
	fd = open(mapfile)
	points = []
	proj_fd = Popen("proj %s" % projection, \
			stdin = PIPE, stdout = PIPE, shell = True)

	points = []
	i = 0;
	for line in fd:
		i += 1
		if not imgfile and i == 2:
			imgfile = ntpath.basename(line.strip())
			imgfile = os.path.join(os.path.dirname(mapfile), imgfile)
			info("image file: %s" % imgfile)
			if not os.access(imgfile, os.F_OK):
				raise Exception("can't find img file")
		if not line.startswith("Point"):
			continue
		d = line.split(",")
		for i in range(len(d)):
			d[i] = d[i].strip()
		# map file may contain stupid lines
		# Point10
		# Point10,xy,,,,,,
		# and etc
		if len(d) < 3 or not d[2]:
			continue
		x = d[2]
		y = d[3]
		points.append((x,y))
		signLat = d[8]
		degLat = d[6]
		minLat = d[7]
		signLon = d[11]
		degLon = d[9]
		minLon = d[10]
		lat = "%sd%s%s" % (degLat, minLat, signLat)
		lon = "%sd%s%s" % (degLon, minLon, signLon)
		s = "%s %s\n" % (lon, lat)
		debug(s.strip())
		proj_fd.stdin.write(s)
	proj_fd.stdin.close()

	info("convert points")
	args = ["-a_srs", projection];
	for line in proj_fd.stdout:
		debug(line.strip())
		lon, lat = line.split()
		p = points.pop(0)
		args.extend(["-gcp", p[0], p[1], lon, lat])
	ret = proj_fd.wait()
	if ret:
		raise Exception("proj failed: return %d" % ret)

	tmp1 = tempfile.mktemp(suffix=".tif", prefix = "mapconverter_")
	try:
		info("execute gdal_translate")
		args.extend([imgfile, tmp1])
		args = ["gdal_translate"] + args
		debug(args)
		gdal_translate = Popen(args)
		ret = gdal_translate.wait()
		if ret:
			raise Exception("gdal_translate failed: return %d" % ret)
		
		tmp2 = tempfile.mktemp(suffix=".tif", prefix = "mapconverter_")
		tmp3 = tempfile.mktemp(suffix=".tif", prefix = "mapconverter_")
		tmp4 = tempfile.mktemp(suffix=".tif", prefix = "mapconverter_")
		try:
			gdalwarp(tmp1, tmp2)

			gdal_translate2(tmp2, tmp3)
		finally:
			if os.access(tmp2, os.F_OK):
				debug("delete file %s" % tmp2)
				os.unlink(tmp2)
		cmd = ["convert", "-depth", "8", "-type", "Palette", tmp3, tmp4]
		debug(cmd)
		fd = Popen(cmd)
		ret = fd.wait()
		if ret:
			raise Exception("convert failed. exit code = %d" % ret)
		tmp5 = tempfile.mktemp(suffix=".data", prefix = "mapconverter_")
		f = open(tmp5, "w")
		cmd = ["listgeo", "-no_norm", tmp3]
		debug(cmd)
		fd = Popen(cmd, stdout = f)
		ret = fd.wait()
		if ret:
			raise Exception("listgeo failed. exit code = %d" % ret)
		f.close()
		cmd = ["geotifcp", "-g", tmp5, tmp4, outfile]
		debug(cmd)
		fd = Popen(cmd)
		ret = fd.wait()
		if ret:
			raise Exception("geotifcp failed. exit code = %d" % ret)


	finally:
		if os.access(tmp1, os.F_OK):
			debug("delete file %s" % tmp1)
			os.unlink(tmp1)
		if os.access(tmp3, os.F_OK):
			debug("delete file %s" % tmp3)
			os.unlink(tmp3)
		if os.access(tmp4, os.F_OK):
			debug("delete file %s" % tmp4)
			os.unlink(tmp4)
		if os.access(tmp5, os.F_OK):
			debug("delete file %s" % tmp5)
			os.unlink(tmp5)

parser = OptionParser()

parser.add_option('-v', '--verbose', action="store_true",
		help = 'print debug info')
parser.add_option('-o', '--out-file', default = None, \
		help = "result geotiff map",
		type = 'string')
parser.add_option('-i', '--in-file', default = None, \
		help = "converted map file.",
		type = 'string')
parser.add_option('--in-img', default = None, \
		help = "map image file",
		type = 'string')


options, args = parser.parse_args()
if not options.in_file:
	parser.print_help()
	parser.error( ("The options -i is obligatory!") )

if options.verbose:
	logging.getLogger().setLevel(logging.DEBUG)
else:
	logging.getLogger().setLevel(logging.INFO)

convert_ozi_map(options.in_file, options.in_img, options.out_file)
