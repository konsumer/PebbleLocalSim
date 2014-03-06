#!/usr/bin/env python2
# encoding: utf-8

# This is free and unencumbered software released into the public domain.
# 
# Anyone is free to copy, modify, publish, use, compile, sell, or
# distribute this software, either in source code form or as a compiled
# binary, for any purpose, commercial or non-commercial, and by any
# means.
# 
# In jurisdictions that recognize copyright laws, the author or authors
# of this software dedicate any and all copyright interest in the
# software to the public domain. We make this dedication for the benefit
# of the public at large and to the detriment of our heirs and
# successors. We intend this dedication to be an overt act of
# relinquishment in perpetuity of all present and future rights to this
# software under copyright law.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# IN NO EVENT SHALL THE AUTHORS BE LIABLE FOR ANY CLAIM, DAMAGES OR
# OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
# ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
# OTHER DEALINGS IN THE SOFTWARE.
# 
# For more information, please refer to <http://unlicense.org/>

import os
import re
import sys
import json
import errno
import struct
import logging
from distutils.spawn import find_executable

__author__    = 'René Köcher <shirk@bitspin.org>'
__copyright__ = 'Placed in the public domain with the hope that it will be useful.'
__doc__       = 'resCompiler replacement for PebbleLocalSim written in pure python.'

try:
    # locate PebbleSDK so we can profit from their code :)
    path=os.path.dirname(find_executable('pebble'))
    sdk_tools_path = os.path.join(path, '..', 'Pebble', 'tools')
    if os.path.exists(os.path.join(sdk_tools_path, 'bitmapgen.py')):
        sys.path.append(sdk_tools_path)
    import bitmapgen # safest way to convert bitmap resources..
except ImportError as e:
    logging.basicConfig(format='[%(levelname)-8s] %(message)s', level=logging.INFO)
    logging.fatal('Unable to detect PebbleSDK, make sure it is in your PATH!')
    sys.exit(1)

class ResourceCompiler(object):
	VERSION_DEF_MAXLEN      = 63
	FRIENDLY_VERSION_MAXLEN = 32
	RESOURCES_MAX_COUNT     = 32
	RESOURCE_NAME_MAXLEN    = 63
	RESOURCE_FILE_MAXLEN    = 63
	PNG_TRANS_POSTFIX_LEN   = 6
	RESOURCE_HEADER_OUTLINE = """#pragma once

// AUTOGENERATED BY tools/local/resCompiler
// DO NOT MODIFY
//

#include <stdint.h>
/* Because for some reasons (perhaps SDL?) changing the entry point creates crashes,
 * but because pebble.h includes this file and all your pebble apps include pebble.h
 * I change the name of your "main" function to "pbl_main"
 */
#undef main
#define main pbl_main
typedef enum {
	INVALID_RESOURCE = 0,
%s
} ResourceId;
"""
	RESOURCE_ID_STR     = "	RESOURCE_ID_%s,\n"
	RESOURCE_ID_STR_0   = "	RESOURCE_ID_%s = 0,\n"

	def __init__(self, res_handle, out_path):
		self._handle = res_handle
		self._res_count = 0
		self._res_names = []
		self._out_path = out_path

	def _compile_resource_map(self):
		try:
			self._json = json.loads( self._handle.read() )
		except ValueError as e:
			logging.error('Resource map syntax is invalid: %s', e.message)
			return False

		if not self._json.has_key('resources'):
			logging.error('Resource map invalid (No object "resources" was found)')
			return False

		if not self._json['resources'].has_key('media'):
			logging.error('Resource map invalid (No object "media" was found in "resources")')
			return False

		res_out_idx=0
		for (i, res_def) in enumerate(self._json['resources']['media']):
			for req_key in ['name','file','type']:
				# check for all required keys
				if not res_def.has_key(req_key):
					logging.error('Resource map invalid (Resource #%d: string "%s" was not found)', i, req_key)
					return False

			if len(res_def['name']) > ResourceCompiler.RESOURCE_NAME_MAXLEN:
				logging.error('Resource map invalid (Resource #%d: name is too long)', i)
				return False

			if len(res_def['file']) > ResourceCompiler.RESOURCE_FILE_MAXLEN:
				logging.error('Resource map invalid (Resource #%d: file name is too long)', i)
				return False

			if not res_def['type'] in ['raw', 'png', 'png-trans', 'font']:
				logging.error('Resource map invalid (Resource #%d: invalid resource type)', i)
				return False

			if res_def['type'] == 'raw':
				if not self._handle_raw(res_out_idx, res_def):
					return False

			elif res_def['type'] == 'png':
				if not self._handle_png(res_out_idx, res_def):
					return False

			elif res_def['type'] == 'png-trans':
				if len(res_def['name']) + ResourceCompiler.PNG_TRANS_POSTFIX_LEN > ResourceCompiler.RESOURCE_FILE_MAXLEN:
					logging.error('Resource map invalid (Resource #%d: name is too long for a png-trans name)', i)
					return False
				
				if not self._handle_trans_png(res_out_idx, res_def):
					return False

				res_out_idx += 1 # transparency requires 2 output resources

			elif res_def['type'] == 'font':
				if not self._handle_font(res_out_idx, res_def):
					return False

			res_out_idx += 1
		return True

	def _handle_raw(self, idx, res_def):
		# FIXME: could just copy the original file...
		res_path = os.path.join(self._out_path, 'resources', res_def['file'])
		out_path = os.path.join(self._out_path, 'build', 'local', 'resources', '%d' % idx)
		try:
			res_handle = open(res_path, 'rb')
		except OSError as e:
			logging.error('Couldn\'t open raw resource input file "%s": [Errno %d] %s',
			              res_path, e.errno, e.strerror)
			return False

		try:
			out_handle = open(out_path, 'wb')
		except OSError as e:
			logging.error('Couldn\'t open raw resource output file "%s": [Errno %d] %s',
			              out_path, e.errno, e.strerror)
			return False

		out_handle.write(res_handle.read())
		out_handle.close()
		res_handle.close()
		return True

	def _handle_png(self, idx, res_def):
		res_path = os.path.join(self._out_path, 'resources', res_def['file'])
		out_path = os.path.join(self._out_path, 'build', 'local', 'resources', '%d' % idx)

		try:
			out_handle = open(out_path, 'wb')
		except OSError as e:
			logging.error('Couldn\'t open raw resource output file "%s": [Errno %d] %s',
			              out_path, e.errno, e.strerror)
			return False

		# fallback to the SDK, they now how bitmaps should look like
		try:
			bitmap = bitmapgen.PebbleBitmap(res_path)
		except IOError as e:
			logging.error('Couldn\'t load png input file "%s": [Errno %d] %s',
			               res_path, e.errno, e.strerror)
			return False

		out_handle.write(bitmap.pbi_header())
		out_handle.write(bitmap.image_bits())
		out_handle.close()
		return True

	def _handle_trans_png(self, idx, res_def):
		res_path = os.path.join(self._out_path, 'resources', res_def['file'])
		wout_path = os.path.join(self._out_path, 'build', 'local', 'resources', '%d' % idx)
		bout_path = os.path.join(self._out_path, 'build', 'local', 'resources', '%d' % (idx + 1))

		try:
			bout_handle = open(bout_path, 'wb')
		except OSError as e:
			logging.error('Couldn\'t open raw resource output file "%s": [Errno %d] %s',
			              bout_path, e.errno, e.strerror)
			return False

		try:
			wout_handle = open(wout_path, 'wb')
		except OSError as e:
			logging.error('Couldn\'t open raw resource output file "%s": [Errno %d] %s',
			              wout_path, e.errno, e.strerror)
			bout_handle.close()
			return False

		# fallback to the SDK, they now how bitmaps should look like
		try:
			black_map = bitmapgen.PebbleBitmap(res_path, bitmapgen.BLACK_COLOR_MAP)
			white_map = bitmapgen.PebbleBitmap(res_path, bitmapgen.WHITE_COLOR_MAP)
		except IOError as e:
			logging.error('Couldn\'t load png input file "%s": [Errno %d] %s',
			               res_path, e.errno, e.strerror)
			wout_handle.close()
			bout_handle.close()
			return False

		bout_handle.write(black_map.pbi_header())
		bout_handle.write(black_map.image_bits())
		bout_handle.close()

		wout_handle.write(white_map.pbi_header())
		wout_handle.write(white_map.image_bits())
		wout_handle.close()
		return True

	def _handle_font(self, idx, res_def):
		# determine the fontheight up-front
		match = re.match(r'.*[^0-9]([0-9]+)$', res_def['name'])
		if not match:
			logging.error('Resource #%d: Font definition name is invalid (Size has to be stated at the end)', idx)
			return False
		font_size = long(match.groups()[0])

		# FIXME: could just copy the original file...
		res_path = os.path.join(self._out_path, 'resources', res_def['file'])
		out_path = os.path.join(self._out_path, 'build', 'local', 'resources', '%d_f' % idx)
		siz_path = os.path.join(self._out_path, 'build', 'local', 'resources', '%d' % idx)
		try:
			res_handle = open(res_path, 'rb')
		except OSError as e:
			logging.error('Couldn\'t open raw resource input file "%s": [Errno %d] %s',
			              res_path, e.errno, e.strerror)
			return False

		try:
			out_handle = open(out_path, 'wb')
		except OSError as e:
			logging.error('Couldn\'t open raw resource output file "%s": [Errno %d] %s',
			              out_path, e.errno, e.strerror)
			res_handle.close()
			return False
		try:
			siz_handle = open(siz_path, 'wb')
		except OSError as e:
			logging.error('Couldn\'t open raw resource output file "%s": [Errno %d] %s',
			              out_path, e.errno, e.strerror)
			res_handle.close()
			out_handle.close()
			return False

		out_handle.write(res_handle.read())
		out_handle.close()
		res_handle.close()

		siz_handle.write(struct.pack('@i', font_size))
		siz_handle.close()
		return True

	def _generate_resource_header(self):
		out_path = os.path.join(self._out_path, 'build', 'tempLocal', 'src', 'resource_ids.auto.h')
		try:
			out_handle = open(out_path, 'wb')
		except OSError as e:
			logging.error('Couldn\'t open header file "%s": [Errno %d] %s',
			              out_path, e.errno, e.strerror)
			return False

		res_strings = ""
		res_fmt_str = ResourceCompiler.RESOURCE_ID_STR
		for (n, res_def) in enumerate(self._json['resources']['media']):
			if n == 0:
				res_fmt_str = ResourceCompiler.RESOURCE_ID_STR_0
			else:
				res_fmt_str = ResourceCompiler.RESOURCE_ID_STR

			if res_def['type'] == 'png-trans':
				res_strings += res_fmt_str % (res_def['name'] + '_WHITE')
				res_fmt_str  = ResourceCompiler.RESOURCE_ID_STR
				res_strings += res_fmt_str % (res_def['name'] + '_BLACK')
			else:
				res_strings += res_fmt_str % res_def['name']

		out_handle.write(ResourceCompiler.RESOURCE_HEADER_OUTLINE % res_strings)
		out_handle.close()
		return True

	def compile(self):
		# create build dirs
		for path in [['build', 'local', 'resources'], ['build', 'tempLocal', 'src']]:
			path = [ self._out_path ] + path
			target_path = os.path.join(*path)
			try:
				os.makedirs(target_path)
			except OSError as e:
				if e.errno == errno.EEXIST:
					pass
				else:
					logging.error('Could not create path "%s": [Errno %d] %s',
					               target_path, e.errno, e.strerror)
					return 1

		if not self._compile_resource_map():
			return 2

		if not self._generate_resource_header():
			return 3
		return 0

if __name__ == '__main__':
	logging.basicConfig(format='[%(levelname)-8s] %(message)s', level=logging.INFO)

	appinfo = './appinfo.json'
	if not os.path.exists(appinfo):
		if len(sys.argv) >= 1 and \
		   os.path.exists(sys.argv[1]) and \
		   os.path.basename(sys.argv[1]) == 'appinfo.json':
		   appinfo = sys.argv[1]

	try:
		handle = open(appinfo, 'rb')
	except EnvironmentError as e:
		logging.error('Please execute the local simulator resource compiler in the project main folder!\n')
		raise

	res_comp = ResourceCompiler(handle, os.path.dirname(appinfo))
	sys.exit(res_comp.compile())
