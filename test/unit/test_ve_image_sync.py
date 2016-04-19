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

import mock
import pytest

from f5_image_prep.ve_image_sync import ImageFileNotQcow2
from f5_image_prep.ve_image_sync import LocalFileNonExtant
from f5_image_prep.ve_image_sync import VEImageSync as veis

VEPATH = 'f5_image_prep.ve_image_sync.VEImageSync'
HOMEDIR = '/home/imageprep/f5-openstack-image-prep/'


class FakeImageModel(object):
    id = 'test'


@pytest.fixture
def VEImageSync():
    with mock.patch('f5_image_prep.ve_image_sync.os.path.isfile') as mock_file:
        mock_file.return_value = True
        return veis(mock.MagicMock(), '/test/img.qcow2', '/test.tar')


def test___init__(VEImageSync):
    assert VEImageSync.img_file == '/test/img.qcow2'
    assert VEImageSync.work_dir == '/home/imageprep/'


def test__init__no_img_file():
    with mock.patch('f5_image_prep.ve_image_sync.os.path.isfile') as mock_file:
        mock_file.return_value = False
        with pytest.raises(LocalFileNonExtant) as ex:
            veis(mock.MagicMock(), '/test/img.qcow2', '/test/')
        assert 'Local file /test/img.qcow2 does not exist' in ex.value.message


def test__init_img_file_not_qcow2():
    with mock.patch('f5_image_prep.ve_image_sync.os.path.isfile') as mock_file:
        mock_file.return_value = True
        with pytest.raises(ImageFileNotQcow2) as ex:
            veis(mock.MagicMock(), '/test/img', '/test')
        assert 'Image file given does not have the .qcow2 extension' == \
            ex.value.message


def test__patch_image(VEImageSync):
    with mock.patch('f5_image_prep.ve_image_sync.subprocess.check_output') as \
            mock_subproc:
        mock_subproc.return_value = 0
        with mock.patch('f5_image_prep.ve_image_sync.os.path.isfile') as \
                mock_isfile:
            mock_isfile.return_value = True
            patch_path = VEImageSync._patch_image()
            assert mock_subproc.call_args == \
                mock.call(
                    ['sudo', '/bin/bash',
                     '/home/imageprep/f5-openstack-image-prep/bin/'
                     'patch-image.sh',
                     '-f', '-s', '/test.tar',
                     '-t', '/home/imageprep',
                     '-o', 'os_ready-img.qcow2', '/test/img.qcow2'],
                )
            assert patch_path == '/home/imageprep/os_ready-img.qcow2'


def test__patch_image_imagepatchfailed(VEImageSync):
    from f5_image_prep.ve_image_sync import ImagePatchFailed
    with mock.patch('f5_image_prep.ve_image_sync.subprocess.check_output') as \
            mock_subproc:
        mock_subproc.return_value = 0
        with mock.patch('f5_image_prep.ve_image_sync.os.path.isfile') as \
                mock_isfile:
            mock_isfile.return_value = False
            with pytest.raises(ImagePatchFailed) as ex:
                VEImageSync._patch_image()
            assert ex.value.message == 'Something went terribly wrong. The ' \
                'rc on the image patch command was 0, but no output image ' \
                'was created.'


def test__patch_image_subprocess_failed(VEImageSync):
    with mock.patch('f5_image_prep.ve_image_sync.subprocess.check_output') as \
            mock_subproc:
        mock_subproc.side_effect = OSError('System related error')
        with pytest.raises(OSError) as ex:
            VEImageSync._patch_image()
        assert ex.value.message == 'System related error'


def test__upload_image_to_glance(VEImageSync):
    with mock.patch('f5_image_prep.ve_image_sync.GlanceLib') as mock_glance:
        mock_glance().glance_client.images.create.return_value = \
            FakeImageModel()
        mock_glance().glance_client.images.list.return_value = \
            [FakeImageModel()]
        with mock.patch('__builtin__.open') as mock_file_open:
            mock_file_open.return_value = 'file_content'
            VEImageSync._upload_image_to_glance('img.qcow2')
        assert mock_glance().glance_client.images.create.call_args == \
            mock.call(
                name='img',
                disk_format='qcow2',
                container_format='bare',
                is_public='true',
                data='file_content'
            )


def test__upload_image_to_glance_failed(VEImageSync):
    with mock.patch('f5_image_prep.ve_image_sync.GlanceLib') as mock_glance:
        mock_glance.side_effect = Exception('Something failed.')
        with pytest.raises(Exception) as ex:
            VEImageSync._upload_image_to_glance('test')
        assert ex.value.message == 'Something failed.'


def test_sync_image(VEImageSync):
    with mock.patch(VEPATH + '._patch_image') as mock_patch:
        with mock.patch(VEPATH + '._upload_image_to_glance') as mock_glance:
            mock_patch.return_value = 'prepped_image'
            VEImageSync.sync_image()
    assert mock_patch.call_args == mock.call()
    assert mock_glance.call_args == mock.call('prepped_image')
