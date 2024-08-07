#!/bin/bash

wget -qO - https://artifacts.elastic.co/GPG-KEY-elasticsearch | sudo apt-key add -
apt-get update
apt-get upgrade -y

rm -f /etc/sudoers.d/cloud

# run script to update keys now
/home/ubuntu/update_keys.sh || { echo "Script /home/ubuntu/update_keys.sh could not be run correctly. Generated from \`update_keys.sh\`." | mail -s "Error during VM authorized_keys update" cloud-support@stfc.ac.uk ; }

pakiti2-client
userdel wjc16017 -r
userdel packer -r
userdel admin-wjc16017 -r
userdel mtint -r
userdel admin-bbm17567 -r
userdel bbm17567 -r

rm -f *.rpm *.deb

sudo systemctl enable qemu-guest-agent.service

/bin/rm -f /etc/filebeat/filebeat.yml

#rotate logs
logrotate -f /etc/logrotate.conf
/bin/rm -rf /var/log/*-???????? /var/log/*.gz
#Clear Audit Log and wtmp
/bin/cat /dev/null > /var/log/audit/audit.log
/bin/cat /dev/null > /var/log/wtmp

#Clean out tmp
/bin/rm -rf /tmp/*
/bin/rm -rf /var/tmp/*

#Remove users shell history
/bin/rm -f /home/*/.bash_history
# Force history to writeback a clean buffer, rather than replacing the file we just cleared
/bin/rm -f ~root/.bash_history && history -c && history -w
