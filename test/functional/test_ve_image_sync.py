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

from f5_image_prep.openstack.openstack import get_creds

import pytest
import subprocess
import sys


BIGIPFILE = 'BIGIP-11.6.0.0.0.401.qcow2'
VEIS_SCRIPT = \
    '/home/imageprep/f5-openstack-image-prep/f5_image_prep/ve_image_sync.py'
STARTUP_SCRIPT = \
    '/home/imageprep/f5-openstack-image-prep/lib/f5_image_prep/startup.tar'
TEST_IMG = None


@pytest.fixture
def VEImageSync(request, set_env_vars, glanceclientmanager):
    from f5_image_prep.ve_image_sync import VEImageSync as veis
    set_env_vars

    def delete_image():
        glanceclientmanager.images.delete(TEST_IMG.id)

    request.addfinalizer(delete_image)

    creds = get_creds()
    work_dir = sys.path[0]
    return veis(creds, BIGIPFILE, STARTUP_SCRIPT, work_dir)


def test_image_sync(VEImageSync, glanceclientmanager):
    global TEST_IMG
    TEST_IMG = VEImageSync.sync_image()
    imgs = glanceclientmanager.images.list()
    assert TEST_IMG.id in [img.id for img in imgs]


def test_image_sync_command_line():
    output = subprocess.check_output(
        ['python', VEIS_SCRIPT, '-i', BIGIPFILE, '-s', STARTUP_SCRIPT]
    )
    assert 'Patching image...' in output
    assert 'Uploading patched image to glance...' in output
    assert 'Image Model:' in output
