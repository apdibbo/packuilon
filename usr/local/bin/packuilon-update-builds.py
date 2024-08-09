import json
import sys
import os
import openstack
import requests
from datetime import datetime
from subprocess import Popen, PIPE
from syslog import syslog, LOG_ERR, LOG_INFO
from configparser import ConfigParser
import time

env = os.environ.copy()

syslog(LOG_INFO, 'Starting')

# Config
configparser = ConfigParser()
try:
    configparser.read('/etc/packer-utils/config.ini')
    PACKER_TEMPLATE_MAP = configparser.get('rabbit2packer', 'PACKER_TEMPLATE_MAP')
    PACKER_PATH = configparser.get('rabbit2packer', 'PACKER_PATH')
    LOG_DIR = configparser.get('rabbit2packer', 'LOG_DIR')
    BUILD_FILE_DIR = configparser.get('rabbit2packer', 'BUILD_FILE_DIR')
    PACKER_AUTH_FILE = configparser.get('rabbit2packer', 'PACKER_AUTH_FILE')
    IMAGES_CONFIG = configparser.get('rabbit2packer', 'IMAGES_CONFIG')
    FLAVOR_NAME = configparser.get('global', 'FLAVOR_NAME')
    NETWORK_ID = configparser.get('global', 'NETWORK_ID')
except Exception as e:
    print("Loading Config File: " + e)
    syslog(LOG_ERR, 'Error reading config file')
    syslog(LOG_ERR, repr(e))
    sys.exit(1)

conn = openstack.connect("packer")


def load_images():
    try:
        with open(IMAGES_CONFIG) as images_JSON:
            IMAGES = json.load(images_JSON)
        return IMAGES
    except IOError as e:
        print("Opening sources file: " + e)
        syslog(LOG_ERR, repr(e))
        syslog(LOG_ERR, "Could not open images config file.")
        sys.exit(1)
    except ValueError as e:
        print("Opening sources file: " + e)
        syslog(LOG_ERR, repr(e))
        syslog(LOG_ERR, "Could not decode images config file, malformed json?")
        sys.exit(1)

def load_templates():
    try:
        with open(PACKER_TEMPLATE_MAP) as template_map_JSON:
            TEMPLATE_MAP = json.load(template_map_JSON)
            return TEMPLATE_MAP
    except IOError as e:
        print("Opening templates file: " + e)
        syslog(LOG_ERR, repr(e))
        syslog(LOG_ERR, "Could not open template map file.")
        sys.exit(1)
    except ValueError as e:
        print("Opening templates file: " + e)
        syslog(LOG_ERR, repr(e))
        syslog(LOG_ERR, "Could not decode template map file, malformed json?")
        sys.exit(1)


IMAGES=load_images()
TEMPLATES=load_templates()


print(TEMPLATES)
for template in TEMPLATES:
    if template != "DEFAULT":
        if template not in IMAGES:
             IMAGES[template] = { "name": template}
        print(template)
        imagedata = conn.image.find_image(IMAGES[template]["name"], ignore_missing=False)
        IMAGES[template]["ID"] = imagedata.id
        previousimagedata = conn.image.find_image(template, ignore_missing=False)
        properties = previousimagedata.properties
        KNOWN_KEYS = ["AQ", "os_", "aq", "hw_"]
        properties = {k: v for k,v in properties.items() for kk in KNOWN_KEYS if kk in k}
        IMAGES[template]["properties"] = properties
with open(IMAGES_CONFIG, "w") as outfile:
    outfile.write(json.dumps(IMAGES, indent=4))

for template_name in TEMPLATES:
    try:
        print(TEMPLATES[template_name][0])
        with open( TEMPLATES[template_name][0]) as template_file:
            print(template_file)
            template = json.load(template_file)
    except FileNotFoundError as e:
        syslog(LOG_ERR, "Could not find packer template file, exiting")
        syslog(LOG_ERR, repr(e))
        sys.exit(1)
    except IOError as e:
        syslog(LOG_ERR, "Unable to open template file")
        syslog(LOG_ERR, repr(e))
        sys.exit(1)

    template["builders"][0]["instance_metadata"] = IMAGES[template_name]["properties"]
    template["builders"][0]["image_name"] = "Next-" + template_name
    template["builders"][0]["source_image"] = IMAGES[template_name]["ID"]
    template["builders"][0]["flavor"] = FLAVOR_NAME
    template["builders"][0]["networks"] = [ NETWORK_ID ]

    build_file_path=BUILD_FILE_DIR + '/' + template_name + ".json"
    log_file_path=LOG_DIR + '/' + template_name + ".log"

    templatejson = json.dumps(template)
    try:
        with open( build_file_path, "wt") as buildFile:
            buildFile.write(templatejson)
    except IOError as e:
        syslog(LOG_ERR, "Unable to write build file: %s" %  build_file_path )
        syslog(LOG_ERR, repr(e))
        sys.exit(1)
