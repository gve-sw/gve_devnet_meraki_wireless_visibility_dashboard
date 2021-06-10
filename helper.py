import requests
import datetime
from dotenv import load_dotenv
import os
import json

# load all environment variables
load_dotenv()
MERAKI_API_KEY = os.getenv("MERAKI_API_KEY")

headers = dict()
headers['Content-Type'] = "application/json"
headers['Accept'] = "application/json"
headers['X-Cisco-Meraki-API-Key'] = MERAKI_API_KEY
base_url = "https://api.meraki.com/api/v1"

#Helper functions

#Returns location and time of accessing device
def getSystemTimeAndLocation():
    #request user ip
    userIPRequest = requests.get('https://get.geojs.io/v1/ip.json')
    userIP = userIPRequest.json()['ip']

    #request geo information based on ip
    geoRequestURL = 'https://get.geojs.io/v1/ip/geo/' + userIP + '.json'
    geoRequest = requests.get(geoRequestURL)
    geoData = geoRequest.json()

    #create info string
    location = geoData['country']
    timezone = geoData['timezone']
    current_time=datetime.datetime.now().strftime("%d %b %Y, %I:%M %p")
    timeAndLocation = "System Information: {}, {} (Timezone: {})".format(location, current_time, timezone)

    return timeAndLocation


#Generic API call function
def meraki_api(method, uri, payload=None):
    response = requests.request(method, base_url+uri, headers=headers, data=json.dumps(payload))
    return response

#Calculate time between 2 days
def time_between(d1, d2):
    return int((d2 - d1).total_seconds())
