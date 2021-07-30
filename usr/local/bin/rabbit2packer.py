#!/usr/bin/python
import sys
import os
import pika
from syslog import syslog, LOG_ERR, LOG_INFO
from configparser import SafeConfigParser
from subprocess import Popen, PIPE
from datetime import datetime
import subprocess  
import threading
import time
import json
import smtplib
import ssl

sslcontext = ssl.create_default_context()

syslog(LOG_INFO, 'Starting')

env=os.environ.copy()

def cl(c):
    p = Popen(c, shell=True, stdout=PIPE, env=env)
    print(c)
    return p.communicate()[0]


def SendMail(Subject , Body, Recipient):
    body_str_encoded_to_byte = Body.encode()
    print("mail -s \"" + Subject + "\" "+ Recipient + " < " + body_str_encoded_to_byte)
    return_stat = cl("mail -s \"" + Subject + "\" " + Recipient + " < "+body_str_encoded_to_byte)
    print(return_stat)

# Config
configparser = SafeConfigParser()
try:
    configparser.read('/etc/packer-utils/config.ini')
    THREAD_COUNT = configparser.getint('rabbit2packer','THREAD_COUNT')
    if (THREAD_COUNT < 1):
        raise UserWarning('A thread count < 1 is defined, no worker threads will run')
    PACKER_TEMPLATE_MAP = configparser.get('rabbit2packer', 'PACKER_TEMPLATE_MAP')
    PACKER_PATH = configparser.get('rabbit2packer', 'PACKER_PATH')
    LOG_DIR = configparser.get('rabbit2packer', 'LOG_DIR')
    BUILD_FILE_DIR = configparser.get('rabbit2packer', 'BUILD_FILE_DIR')
    PACKER_AUTH_FILE = configparser.get('rabbit2packer', 'PACKER_AUTH_FILE')
    QUEUE = configparser.get('global', 'QUEUE')
    IMAGES_CONFIG = configparser.get('rabbit2packer', 'IMAGES_CONFIG')
    RABBIT_HOST = configparser.get('global', 'RABBIT_HOST')
    RABBIT_PORT = configparser.getint('global', 'RABBIT_PORT')
    RABBIT_USER = configparser.get('global', 'RABBIT_USER')
    RABBIT_PW = configparser.get('global', 'RABBIT_PW')
    success_address = configparser.get('global', 'SUCCESS_ADDRESS')
    failure_address = configparser.get('global', 'FAILURE_ADDRESS')
except Exception as e:
    syslog(LOG_ERR, 'Error reading config file')
    syslog(LOG_ERR, repr(e))
    sys.exit(1)

#try:
#    print(SMTP_SERVER)
#    print(int(SMTP_PORT))
#    smtp = smtplib.SMTP(host=SMTP_SERVER, port=int(SMTP_PORT))
#    print("SMTP object created")
#    smtp.starttls(context=sslcontext)
#    print("SMTP TLS Started")
#    smtp.login(SMTP_USER, SMTP_PASSWORD)
#    print("SMTP Login Succeeded")
#    
#except:
#    syslog(LOG_ERR, "Failed to connect to SMTP server")
def load_templates_images():
    try:
        with open(IMAGES_CONFIG) as images_JSON:    
            IMAGES = json.load(images_JSON)
    except IOError as e:
        syslog(LOG_ERR, repr(e))
        syslog(LOG_ERR, "Could not open images config file.")
        sys.exit(1)
    except ValueError as e:
        syslog(LOG_ERR, repr(e))
        syslog(LOG_ERR, "Could not decode images config file, malformed json?")
        sys.exit(1)

    try:
        with open(PACKER_TEMPLATE_MAP) as template_map_JSON:    
            TEMPLATE_MAP = json.load(template_map_JSON)
    except IOError as e:
        syslog(LOG_ERR, repr(e))
        syslog(LOG_ERR, "Could not open template map file.")
        sys.exit(1)
    except ValueError as e:
        syslog(LOG_ERR, repr(e))
        syslog(LOG_ERR, "Could not decode template map file, malformed json?")
        sys.exit(1)

load_templates_images()

exitFlag = 0

class imageBuilder:
    def __init__(self, profile_object):
        self.personality = profile_object["system"]["personality"]["name"]
        #self.os_string = profile_object["system"]["aii"]["nbp"]["pxelinux"]["kernel"].split('/')[0]
        self.os = profile_object["system"]["os"]["distribution"]["name"]
        self.os_ver = profile_object["system"]["os"]["version"]["name"] + "-" + profile_object["system"]["os"]["architecture"]
        self.os_string = self.os + self.os_ver
        self.prettyname = profile_object["system"]["network"]["hostname"]
        syslog(LOG_INFO, "Name is :" + self.prettyname)
        syslog(LOG_INFO, str(IMAGES))
        syslog(LOG_INFO, "OS_STRING = " +self.os_string)
#       for os in IMAGES:
        syslog(LOG_INFO, "OS is :" + self.os)
#           if self.os_string.startswith(os):
#               for ver in IMAGES[os]:
        syslog(LOG_INFO, "OS VER is :" + self.os_ver)
#                   if self.os_string == os + ver:
#                       self.os = os
#                       self.os_ver = ver
        load_templates_images()
        self.imageID = IMAGES[self.os][self.os_ver]
        if not (self.os and self.os_ver):
            raise KeyError('os and os_ver not found in the source image dict')
    def name(self):
#        return "%s-%s" % (self.personality, self.os_string)
        return "%s" % (self.prettyname)
    def prettyName(self):
#        return "%s %s" % (self.os_string, self.personality)
        return "%s" % (self.prettyname)
    def imageID(self):
        return self.imageID
    def metadata(self):
        self.metadata = '"AQ_PERSONALITY": "%s",\n' % self.personality
        self.metadata += '"AQ_OS": "%s",\n' % self.os
        self.metadata += '"AQ_OSVERSION": "%s"\n' % self.os_ver
        return self.metadata

class workerThread (threading.Thread):
    def __init__(self, name):
        threading.Thread.__init__(self)

        self.name = name
    def run(self):
        syslog(LOG_INFO, "Starting " + self.name)
        credentials = pika.PlainCredentials(RABBIT_USER,RABBIT_PW)
        parameters = pika.ConnectionParameters(RABBIT_HOST,
                                       RABBIT_PORT,
                                       "/",
                                       credentials,
                                       connection_attempts=10,
                                       retry_delay=2)
        connection = pika.BlockingConnection(parameters)

        channel = connection.channel()
        channel.queue_declare(
            queue=QUEUE, 
            durable=True
        )

        worker_loop(self.name, channel)
        syslog(LOG_ERR, "Exiting " + self.name)


def worker_loop(threadName, channel):
    while not exitFlag:
        try:
            method_frame, header_frame, body = channel.basic_get(QUEUE)
        except pika.exceptions.ConnectionClosed as e:
            credentials = pika.PlainCredentials(RABBIT_USER,RABBIT_PW)
            parameters = pika.ConnectionParameters(RABBIT_HOST,
                                           RABBIT_PORT,
                                           "/",
                                           credentials,
                                           connection_attempts=10,
                                           retry_delay=2)
            connection = pika.BlockingConnection(parameters)

            channel = connection.channel()
            channel.queue_declare(
                queue=QUEUE,
                durable=True
            )
            syslog(LOG_INFO, threadName + ": reconnecting to channel")
            continue

        if method_frame:
            channel.basic_ack(method_frame.delivery_tag)
            try:
                profile_object = json.loads(body.decode())
            except ValueError as e:
                syslog(LOG_ERR, repr(e))
                syslog(LOG_ERR, threadName + ": could not decode profile, malformed json? Continuing")
                continue

            try:
                image = imageBuilder(profile_object)
            except KeyError as e:
                syslog(LOG_ERR, repr(e))
                syslog(LOG_ERR, threadName + ": source imge was not found, check IMAGES_CONFIG. Continuing")
                continue
            syslog(LOG_ERR, "%s processing %s" % (threadName, image.name()))
            run_packer_subprocess(threadName, image)
            
        time.sleep(2)


def run_packer_subprocess(threadName, image):

    image_name=image.name()
    image_display_name=image.prettyName()
    image_metadata=image.metadata()
        
    try:
        source_image_ID = image.imageID
    except KeyError as e:
        syslog(LOG_ERR, "Source image for " + image_name + " not defined in " + IMAGES_CONFIG + ". Skipping build")
        syslog(LOG_ERR, "Check for relevant OS entry in " + IMAGES_CONFIG)
        return

    templates = TEMPLATE_MAP.get(image_name)

    if templates is None:        
        templates = TEMPLATE_MAP.get("DEFAULT")
        syslog(LOG_INFO, "No Packer template defined for " + image_name + ". Using the default values")

    if templates is None:        
        syslog(LOG_INFO, "No Packer template defined for Default values. No builds will occur.")

    for template in templates:
        template_name=template.rsplit('/', 1)[-1]
        try:
            with open( template, "rt") as template_file:
                template = template_file.read()
        except FileNotFoundError as e:
            syslog(LOG_ERR, "Could not find packer template file, exiting")
            syslog(LOG_ERR, repr(e))
            sys.exit(1)
        except IOError as e:
            syslog(LOG_ERR, "Unable to open template file")
            syslog(LOG_ERR, repr(e))
            sys.exit(1)

        template = template.replace("$METADATA", image_metadata)
        template = template.replace("$NAME", image_display_name)
        template = template.replace("$IMAGE", source_image_ID)

        #"AQ_ARCHETYPE": "$ARCHETYPE",
        #                "AQ_DOMAIN": "$DOMAIN",
        #                "AQ_OS": "$OS",
        #                "AQ_OSVERSION": "$OSVERSION",
        #                "AQ_PERSONALITY": "$PERSONALITY",
        #                "AQ_SANDBOX": "$SANDBOX"

        DATE = datetime.now().strftime("%d-%m-%Y-%H-%M-%S")

        build_file_path=BUILD_FILE_DIR + '/' + image_name + "." + template_name + ".json"
        log_file_path=LOG_DIR + '/' + image_name + "." + template_name + ".log"
        mailfilepath="/tmp/"+image_name+"-"+DATE+".mail"


        try:
            with open( build_file_path, "wt") as buildFile:
                buildFile.write(template)
        except IOError as e:
            syslog(LOG_ERR, "Unable to write build file: %s" %  build_file_path )
            syslog(LOG_ERR, repr(e))        
            sys.exit(1)

        try:
            buildLog = open( log_file_path, "wt")
        except IOError as e:
            syslog(LOG_ERR, "Unable to write to build log file: %s" %  log_file_path )
            syslog(LOG_ERR, repr(e))
            sys.exit(1)
        
        packerCmd = ( "source {packer_auth};"
                      "export OS_TENANT_ID=$OS_PROJECT_ID;"
                      "export OS_DOMAIN_NAME=$OS_USER_DOMAIN_NAME;"  
                      "{packer_path} build {build_file}"
                    ).format(
                        packer_auth=PACKER_AUTH_FILE, 
                        build_file=build_file_path,
                        packer_path=PACKER_PATH
                    )
        syslog(LOG_INFO,"Packer Command: " + packerCmd)

        syslog(LOG_INFO, "packer build starting, see: " + log_file_path + " for details")

        packerProc = subprocess.Popen(packerCmd, shell=True, stdout=buildLog, stderr=subprocess.STDOUT, env=env)
        ret_code = packerProc.wait()
        if (ret_code != 0):
            syslog(LOG_ERR, threadName + ": packer exited with non zero exit code, " + image_name + "." + template_name+ " build failed")
            with open(mailfilepath, "w") as mailfile:
                mailfile.write("Build of " + image_name + " failed on " + DATE + " due to rally test failing")
            SendMail("Build Failed - " + image_name, mailfilepath, failure_address)
        else:
            syslog(LOG_INFO, threadName + ": image built successfully: " + image_name + "." + template_name)

threads = []

# Create new threads
for i in range(THREAD_COUNT):
    thread = workerThread("Thread-" + str(i + 1))
    thread.start()
    threads.append(thread)

while True:
    time.sleep(5)







