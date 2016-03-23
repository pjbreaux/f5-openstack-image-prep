# Copyright 2015-2016 F5 Networks Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import argparse
import os
import subprocess

from f5_image_prep.openstack.glance import GlanceLib
from f5_image_prep.openstack.openstack import get_creds


CONTAINERFORMAT = 'bare'
DISKFORMAT = 'qcow2'
PATCHTOOL = '/home/imageprep/f5-openstack-image-prep/bin/patch-image.sh'
STARTUPSCRIPT = \
    '/home/imageprep/f5-openstack-image-prep/lib/f5_image_prep/startup'
STARTUPFUNCS = \
    '/home/imageprep/f5-openstack-image-prep/lib/f5_image_prep/' \
    'os-functions/'
WORKDIR = os.environ['HOME']


class LocalFileNonExtant(Exception):
    pass


class ImageFileNotQcow2(Exception):
    pass


class ImagePatchFailed(Exception):
    pass


class VEImageSync(object):
    '''Handle synchronization of VE glance images.'''

    def __init__(self, creds, imgfile, workdir=WORKDIR):
        '''Initialize a VEImageSync object.

        :param img_location: str -- path to a VE image
        :param userdata_location: str -- path to userdata to configure VE
        '''

        self.os_creds = creds
        self.img_file = imgfile

        if not os.path.isfile(self.img_file):
            msg = 'Local file {} does not exist'.format(self.img_file)
            raise LocalFileNonExtant(msg)
        if not self.img_file.endswith('qcow2'):
            msg = 'Image file given does not have the .qcow2 extension'
            raise ImageFileNotQcow2(msg)

        self.filename = self.img_file.split('/')[-1]
        self.work_dir = workdir
        if not self.work_dir.endswith('/'):
            self.work_dir += '/'

    def _patch_image(self):
        '''Patch image with patch-image-tool

        :returns: str -- local of patched image file
        '''

        print('\n\nPatching image...\n\n')
        patched_img_name = 'os_ready-' + self.filename
        patch_call = ['sudo', '/bin/bash', PATCHTOOL, '-f',
                      '-s', STARTUPSCRIPT,
                      '-d', STARTUPFUNCS,
                      '-t', self.work_dir[:-1],
                      '-o', patched_img_name,
                      self.img_file]
        subprocess.check_output(patch_call)

        if not os.path.isfile(self.work_dir + patched_img_name):
            msg = 'Something went terribly wrong. The rc on the image patch ' \
                'command was 0, but no output image was created.'
            raise ImagePatchFailed(msg)

        return self.work_dir + patched_img_name

    def _upload_image_to_glance(self, patch_image_location):
        '''Patch image, then upload it to Glance.

        :param image_location: str -- path to image on local file system
        :returns: model of image resource created
        '''

        print('\n\nUploading patched image to glance...\n\n')
        gc = GlanceLib(self.os_creds).glance_client
        img_name = self.filename.replace('.qcow2', '')
        img_model = gc.images.create(
            name=img_name,
            disk_format=DISKFORMAT,
            container_format=CONTAINERFORMAT,
            is_public='true',
            data=open(patch_image_location, 'rb')
        )
        imgs = [img.id for img in gc.images.list()]
        assert img_model.id in imgs
        return img_model

    def sync_image(self):
        '''Entry into syncing VE image to glance.'''

        prepped_image = self._patch_image()
        img_model = self._upload_image_to_glance(prepped_image)
        print('\n\nImage Model:\n')
        print(img_model)
        return img_model


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-i', '--imagefile',
        help='Location (local or otherwise) to VE image file.',
        required=True
    )
    parser.add_argument(
        '-w', '--workingdirectory',
        default="%s" % os.environ['HOME'],
        help='Directory to save working files.'
    )
    args = parser.parse_args()

    creds = get_creds()
    ve_image_sync = VEImageSync(
        creds,
        args.imagefile,
        workdir=args.workingdirectory
    )
    ve_image_sync.sync_image()
