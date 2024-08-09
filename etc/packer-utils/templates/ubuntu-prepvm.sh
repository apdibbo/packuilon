#!/bin/bash

wget -qO - https://artifacts.elastic.co/GPG-KEY-elasticsearch | sudo apt-key add -

/bin/rm -f /etc/filebeat/filebeat.yml
