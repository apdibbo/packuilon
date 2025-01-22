#!/usr/bin/python3
import json
import sys
import os
import openstack
import requests
from datetime import datetime
from subprocess import Popen, PIPE
from configparser import SafeConfigParser
import time
import smtplib

env = os.environ.copy()

next_image_name = sys.argv[1]

current_image_name = next_image_name.replace("Next-", "")

# Read from config file
parser = SafeConfigParser()
parser.read('/etc/packer-utils/config.ini')
auth_file = parser.get('rabbit2packer', 'PACKER_ADMIN_AUTH_FILE')
success_address = parser.get('global', 'SUCCESS_ADDRESS')
failure_address = parser.get('global', 'FAILURE_ADDRESS')
slackhook = parser.get('global', 'SLACK_SUCCESS_HOOK')

conn = openstack.connect("packer")


def cl(c):
    print(c, flush=True)
    p = Popen(c, shell=True, stdout=PIPE, env=env)
    return str(p.communicate()[0])

def SendMail(Subject , Body, Recipient):
#    body_str_encoded_to_byte = Body.encode()
#    print("mail -s \"" + Subject + "\" "+ Recipient + " < " + body_str_encoded_to_byte)
#    return_stat = cl("mail -s \"" + Subject + "\" " + Recipient + " < "+body_str_encoded_to_byte)
    return_stat = cl("mail -s \"" + Subject + "\" " + Recipient + " < "+Body)
#    print(return_stat)

# Commenting out as not picking up host mail config
#def SendMail(Subject, Body, Recipient: str):
#    FROM = "packquilon@example.com"
#    TO = [Recipient]
#
#    message = f"""\
#    From: {FROM}
#    To: {TO}
#    Subject: {Subject}
#
#    {Body}
#    """
#
#    # Send via mailx
#    try:
#        server = smtplib.SMTP('localhost')
#    except OSError:
#        print("Mail server not configured on this machine")
#        return
#    server.set_debuglevel(3)
#    server.sendmail(FROM, TO, message)
#    server.quit()

DATE = datetime.now().strftime("%d-%m-%Y-%H-%M-%S")

print(DATE)

print(next_image_name)
print(current_image_name)
next_image = conn.image.find_image(next_image_name, ignore_missing=False)

with open('/etc/packer-utils/templates/rally-test.json') as templatejson:
    testtemplate = json.load(templatejson)

testtemplate["VMTasks.boot_runcommand_delete"][0]["args"]["image"]["name"] = next_image_name

with open("/etc/packer-utils/tests/" + next_image_name + ".json", "w") as testFile:
    json.dump(testtemplate, testFile)

mailfilepath = "/tmp/" + next_image_name + "-" + DATE + ".mail"

test = cl("INSTANCENAME=Prod; rally db create ;rally deployment create --name $INSTANCENAME --filename /opt/rally/existing.json ;rally deployment check $INSTANCENAME ; /opt/rally/bin/rally deployment use Prod ; /opt/rally/bin/rally task start /etc/packer-utils/tests/" + next_image_name + ".json | grep \"rally task report\" | grep \"json\" | sed 's/output.json/\/tmp\/" + next_image_name + "-" + DATE + "\.json/g'")
print(test)
reportcmd = test.split("\\n\\t")[3].replace("\\n", "").replace("'", "").replace('"','')
print(reportcmd)
print("GENERATING NEW REPORT", flush=True)
#rint(test + " /tmp/"+next_image_name+"-"+DATE+".json")
#cl(test + " /tmp/"+next_image_name+"-"+DATE+".json")

cl(reportcmd)

with open("/tmp/" + next_image_name + "-" + DATE + ".json") as testresultjson:
    testresult = json.load(testresultjson)

testPassed = testresult["tasks"][0]["pass_sla"]

if testPassed:
    print(next_image_name)

    allimages = conn.image.images()
    all_image_names = [image.name for image in allimages]

    private = True
    public = False
    shared = False

    members = []
    images = []

    existing_visibility = "private"

    previous_image = None
    if next_image.name in all_image_names:
        previous_image = conn.image.find_image(current_image_name, ignore_missing=False)
        existing_visibility = previous_image.visibility
    print(existing_visibility)
    properties = dict()
    if previous_image:
        properties = previous_image.properties
        KNOWN_KEYS = ["AQ", "os_", "aq", "hw_"]
        properties = {k: v for k,v in properties.items() for kk in KNOWN_KEYS if kk in k}
    else:
        print("Previous version not found")

    conn.image.update_image(next_image.id, visibility=existing_visibility, **properties)

    if existing_visibility == "shared" and previous_image:
        existing_members = conn.image.members(previous_image)
        for existing_member in existing_members:
            print(existing_member)
            existing_member_string=existing_member["member_id"]
            print("Existing Member = " + existing_member_string)
            new_member = conn.image.add_member(next_image, member_id=existing_member_string)
            conn.image.update_member(new_member, next_image, status="accepted")
    print("Current image: " + previous_image.name)
    print("Next image: " + next_image.name)
    if previous_image:
        conn.image.deactivate_image(previous_image)
        print("Rename " + previous_image.name + " to " + "warehoused-" + previous_image.name + "-" + DATE)
        conn.image.update_image(previous_image.id, name="warehoused-" + previous_image.name + "-" + DATE, is_hidden=True)
        print("Rename " + next_image.name + " to " + current_image_name)
        conn.image.update_image(next_image.id, name=current_image_name)

    # print(images)

    # print(members)

    for image_name in all_image_names:
        if current_image_name.lower() in image_name.lower():
            print("sed -i 's/" + previous_image.id + "/" + next_image.id + "/g' /etc/packer-utils/build/*.json")
            cl("sed -i 's/" + previous_image.id + "/" + next_image.id + "/g' /etc/packer-utils/build/*.json")
            print("sed -i 's/" + previous_image.id + "/" + next_image.id + "/g' /etc/packer-utils/source-images.json")
            cl("sed -i 's/" + previous_image.id + "/" + next_image.id + "/g' /etc/packer-utils/source-images.json")

    with open(mailfilepath, "w") as mailfile:
        mailfile.write(
            "Build of " + image_name + " succeeded on " + DATE + ". New image ID is \`" + next_image.id + "\`")
    body="Build of " + image_name + " succeeded on " + DATE + ". New image ID is \`" + next_image.id + "\`"
#    SendMail(current_image_name + " - Build Succeeded", mailfilepath, success_address)

    slackheaders = {'Content-Type': 'application/json'}
    slackdata = {
        'text': "Build of " + current_image_name + " succeeded on " + DATE + ". New image ID is \`" + next_image.id + "\`"}
    slackdebug = requests.post(slackhook, headers=slackheaders, data=json.dumps(slackdata))
    print(slackdebug)


else:
    with open(mailfilepath, "w") as mailfile:
        mailfile.write(f"Build of {next_image_name} failed on {DATE} due to rally test failing")
    body=f"Build of {next_image_name} failed on {DATE} due to rally test failing"
#    SendMail("Build Failed", body, failure_address)
    visibility = " --private "

    conn.image.update_image(next_image.id, visibility=visibility, name="Broken-" + current_image_name + DATE)
