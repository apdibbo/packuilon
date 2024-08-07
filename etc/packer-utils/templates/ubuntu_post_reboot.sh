#!/bin/bash
sudo dpkg --list | egrep -i 'linux-image|linux-headers|linux-modules' | cut -d " " -f 3 | grep -v "$(uname -r)" | grep -v 'linux-headers-generic' | grep -v 'linux-headers-virtual' | grep -v 'linux-image-virtual' | xargs sudo apt-get remove -y
sudo /home/ubuntu/ubuntu-prepvm.sh
