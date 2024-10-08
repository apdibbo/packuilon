#!/bin/sh
#set -x
dnf remove --oldinstallonly kernel -y
/usr/local/bin/prepvm-managed.sh
