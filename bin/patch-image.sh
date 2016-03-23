#!/bin/bash

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

function validate_packages_debian() {
    is_qemu_utils_installed=`dpkg --get-selections qemu-utils|grep install|wc -l`
    is_lvm2_installed=`dpkg --get-selections lvm2|grep install|wc -l`    
    if ! [ $is_qemu_utils_installed == 1 -a  $is_lvm2_installed == 1 ]; then 
        echo Running apt-get update....
        sudo apt-get update > /dev/null
        echo Running apt-get -y install qemu-utils lvm2
        sudo apt-get -y install qemu-utils lvm2
    fi
}

function validate_packages_redhat() {
    qemu_img_not_installed=`rpm -q qemu-img|grep "not installed"|wc -l`
    lvm2_not_installed=`rpm -q lvm2|grep "not installed"|wc -l`
    sudo_not_installed=`rpm -q sudo|grep "not installed"|wc -l`
    if [ $qemu_img_not_installed == 1 -o $lvm2_not_installed == 1 -o $sudo_not_installed == 1 ]; then 
        echo Running yum -y install lvm2 qemu-img sudo
        su root -c "yum -y install lvm2 qemu-img sudo"
    fi
    user=`whoami`
    if ! [ "$user" == "root" ]; then
        echo Adding user to sudoers
        su root -c "echo '${user} ALL=(ALL) ALL' >> /etc/sudoers"
    fi
}

function get_distribution_type()
{
    local dtype
    # Assume unknown
    dtype="unknown"

    # First test against Fedora / RHEL / CentOS / generic Redhat derivative
    if [ -s /etc/redhat-release ]; then
        dtype="redhat"
    # Then test against Debian, Ubuntu and friends
    elif [ -s /etc/debian_version ]; then
        dtype="debian"
    fi
    echo $dtype
}

function validate_packages() {
    distro=`get_distribution_type`
    if [ "$distro" == "debian" ]; then
       validate_packages_debian
    fi
    if [ "$distro" == "redhat" ]; then
        lsmod | grep -q ^nbd
        if [ $? -ne 0 ]; then
            echo "CentOS and REHL stock kernels don't include ndb (network block device) module support."
            echo "Suggestion is to use a Ubuntu workstation, for F5 VE image patching."
            exit 1
        fi
        validate_packages_redhat
    fi
    if [ "$distro" == "unknown" ]; then
        echo These tools only run on Debian or RHEL based distributions
        exit 1
    fi
}

function validate_inputs() {
    if ! [ -f $startup_file ]; then
        echo "startup file $startup_file does not exist"
        badusage
    fi

    if ! [ -d $startup_functions ]; then
        echo "startup functions directory does not exist"
        badusage
    fi

    if ! [ $userdata_file == 'none' ]; then
        if ! [ -f $userdata_file ]; then
            echo "default userdata JSON file $userdata_file does not exist"
            badusage
        fi
    fi

    if [ -n "$baseisofile" -a -z "$hotfixisofile" ]; then
        echo "Must specify hotfix iso when base iso specified"
        badusage
    fi

    if [ -n "$hotfixisofile" -a -z "$baseisofile" ]; then
        echo "Must specify base iso when hotfix iso specified"
        badusage
    fi
}

function get_dev() {
    ls -l /dev/vg-db-hda | grep $1 | cut -d'>' -f2 | cut -d'/' -f2-
}

function inject_files() {
    if [ -f $startup_file ]; then
        cp $startup_file /mnt/bigip-config/startup
    fi

    if [ -d "$startup_functions" ]; then
        cp -R $startup_functions /mnt/bigip-config/
    fi

    if $firstboot_file; then
        touch /mnt/bigip-config/firstboot > /dev/null 2>&1
    fi
    if [ -f $userdata_file ]; then
        cp $userdata_file /mnt/bigip-config
    fi

    if [ -n "$baseisofile" ]; then
        mount /dev/`get_dev dat.share` /mnt/bigip-shared
        cp $baseisofile /mnt/bigip-shared/images
        cp $hotfixisofile /mnt/bigip-shared/images
    fi

    if [ -n "$baseisofile" ]; then
        if [ ! -f "$baseisofile" ]; then
            if [ ! -f "$temp_dir/../added/$baseisofile" ]; then
                echo "Can't find base iso file $baseisofile"
                badusage
            else
                baseisofile="$temp_dir/../added/$baseisofile"
            fi
        fi
    fi
    if [ -n "$hotfixisofile" ]; then
        if [ ! -f "$hotfixisofile" ]; then
            if [ ! -f "$temp_dir/../added/$hotfixisofile" ]; then
                echo "Can't find hotfix iso file $hotfixisofile"
                badusage
            else
                hotfixisofile="$temp_dir/../added/$hotfixisofile"
            fi
        fi
    fi

}

function load_nbd() {
    is_nbd_loaded=`lsmod|grep nbd|wc -l`

    if [ $is_nbd_loaded == 0 ]; then
        modprobe nbd max_part=32
    fi
}

temp_dir="$HOME/.f5-image-prep/tmp"
userdata_file='none'
firstboot_file=false
startup_functions=''

function badusage {
    echo "usage: patch-image -s startup_file -d startup_functions -f -u userdata_file <image.qcow2>"
    echo ""
    echo "Options:"
    echo "   -s : [full_path_to_startup_script] : user defined startup script"
    echo "   -d : [full_path_to_startup_script] : user defined startup script functions"
    echo "   -f : touches a /config/firstboot file"
    echo "   -u : [full_path_to_userdata] - user defined default userdata JSON file"
    echo "   -t : [full_path_to_temp_dir] - working directory to patch image"
    echo "   -o : [patched image name] - name given to the patched image file"
    echo "   -b : [base iso name] - base iso to copy to /shared on image"
    echo "   -h : [hotfix iso name] - hotfix iso to copy to /shared on image"
    echo ""
    echo "The image file name must end with .qcow2"
    echo ""
    echo "Example: sudo env PATH=\$PATH HOME=\$HOME patch-image BIGIP-11.6.0.0.0.401.qcow2"
    echo "Example: sudo env PATH=\$PATH HOME=\$HOME patch-image \\"
    echo "      -b BIGIP-11.6.0.0.0.401.iso \\"
    echo "      -h Hotfix-BIGIP-11.6.0.5.0.429-HF5.iso \\"
    echo "      BIGIP-11.6.0.0.0.401.qcow2"
    echo ""
    exit 1
}

if [ $UID -ne 0 ]; then
    echo You must run patch-image with sudo.
    badusage
fi

oldfile="${@: -1}"

# There needs to be a file parameter.  
if [ $# -lt 1 ]; then
    echo You must specify a qcow2 image to patch.
    badusage
else
  # The file parameter must end with .qcow2
  echo $oldfile | grep -e'\(.*\)\.qcow2'
  if [ $? -ne 0 ]; then
      echo You must specify a qcow2 image to patch.
      badusage
  fi
fi

while getopts :s:d:u:ft:o:b:h: opt "$@"; do
  case $opt in
   s)
       startup_file=$OPTARG
       ;;
   d)
       startup_functions=$OPTARG
       ;;
   u)
       userdata_file=$OPTARG
       ;;
   f)
       firstboot_file=true
       ;;
   t)
       temp_dir=$OPTARG
       ;;
   o)
       newfile=$OPTARG
       ;;
   b)
       baseisofile=$OPTARG
       ;;
   h)
       hotfixisofile=$OPTARG
       ;;
   esac
done
      
validate_inputs
load_nbd
validate_packages

# exit on error
set -x

mkdir -p $temp_dir

function newfilename {
    local ofname=$(basename $1)
    if [ -n "$2" ]; then
        local hotfixisofile=$(basename $2)
    else
        local hotfixisofile=
    fi
    #echo using $1 $2
    if [ -z "$hotfixisofile" ]; then
        newfile=$(echo $ofname | sed 's/\(.*\)\.qcow2/\1-OpenStack.qcow2/')
    else
        echo $oldfile | grep -q -e'BIG-IQ\(.*\)'
        if [ $? -eq 0 ]; then
            qcowpattern="BIG-IQ-\([^.]*.[^.]*.[^.]*.[^.]*.[^.]*.[^.]*\).qcow2"
            hotfixpattern="Hotfix-BIG-IQ-[^.]*.[^.]*.[^.]*-\([^.]*.[^.]*.[^.]*\)-.*"
            newpattern="BIG-IQ-\1-HF-\2-OpenStack.qcow2"
        else
            qcowpattern="BIGIP-\([^.]*.[^.]*.[^.]*.[^.]*.[^.]*.[^.]*\).qcow2"
            hotfixpattern="Hotfix-BIGIP-[^.]*.[^.]*.[^.]*.\([^.]*.[^.]*.[^.]*\)-.*"
            newpattern="BIGIP-\1-HF-\2-OpenStack.qcow2"
        fi
        newfile=$(echo $ofname $hotfixisofile | sed "s/$qcowpattern $hotfixpattern/$newpattern/")
    fi
    echo $newfile
}


# did we get a full path?
if [ -f "$oldfile" ]; then
    ofname=`basename $oldfile`
    if [ -z ${newfile} ]; then
        newfile=$(newfilename $ofname $hotfixisofile)
    fi
    cp $oldfile $temp_dir/$newfile
else
    if [ -f "$temp_dir/../added/$oldfile" ]; then
        oldfile="$temp_dir/../added/$oldfile"
        ofname=`basename $oldfile`
        if [ -z ${newfile} ]; then
            newfile=$(newfilename $ofname $hotfixisofile)
        fi
        cp $oldfile $temp_dir/$newfile
    else
        echo "Can't find qcow file $oldfile"
        exit 1
    fi
fi


sleep 2
qemu-nbd -d /dev/nbd0
sleep 2
qemu-nbd --connect=/dev/nbd0 $temp_dir/$newfile
sleep 2
pvscan
sleep 2
echo "The following command may cause 'Can't deactivate' messages."
echo "These do not necessarily indicate a problem."
vgchange -ay
sleep 2
mkdir -p /mnt/bigip-config
if [ -n "$baseisofile" ]; then
    mkdir -p /mnt/bigip-shared
fi

echo "Waiting 15 seconds"
sleep 15

# Unmount config and shared incase previous attempt to patch failed
umount /mnt/bigip-config || [ $? -eq 1 ]
umount /mnt/bigip-shared || [ $? -eq 1 ]

mount /dev/`get_dev set.1._config` /mnt/bigip-config

inject_files

sleep 2
umount /mnt/bigip-config
sleep 2
if [ -n "$baseisofile" ]; then
    umount /mnt/bigip-shared
fi
sleep 2
vgchange -an
sleep 2
qemu-nbd -d /dev/nbd0
echo "Patched image located at $temp_dir/$newfile"
set +x
