import time
from datetime import datetime
import json
from helper import meraki_api
from models import db, APStatus, APClient, APBandwidth, Client
from dotenv import load_dotenv
import os
import smtplib, ssl
import requests

# environment variables
load_dotenv()
SMTP_SERVER = os.getenv("SMTP_SERVER")
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
RECEIVER_EMAIL = os.getenv("RECEIVER_EMAIL")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
AP_STATUS_POLLING_INTERVAL = os.getenv("AP_STATUS_POLLING_INTERVAL")
AP_CLIENT_POLLING_INTERVAL = os.getenv("AP_CLIENT_POLLING_INTERVAL")
AP_BANDWIDTH_POLLING_INTERVAL = os.getenv("AP_BANDWIDTH_POLLING_INTERVAL")
CLIENT_PERFORMANCE_POLLING_INTERVAL = os.getenv("CLIENT_PERFORMANCE_POLLING_INTERVAL")
CLIENT_COUNT_THRESHOLD = os.getenv("CLIENT_COUNT_THRESHOLD")
BANDWIDTH_THRESHOLD = os.getenv("BANDWIDTH_THRESHOLD")
CLIENT_PERFORMANCE_THRESHOLD = os.getenv("CLIENT_PERFORMANCE_THRESHOLD")
SERVICENOW_INSTANCE = os.getenv('SERVICENOW_INSTANCE')
SERVICENOW_USERNAME = os.getenv('SERVICENOW_USERNAME')
SERVICENOW_PASSWORD = os.getenv('SERVICENOW_PASSWORD')
SERVICENOW_INCIDENT_DEFAULT_IMPACT = os.getenv('SERVICENOW_INCIDENT_DEFAULT_IMPACT')
SERVICENOW_INCIDENT_DEFAULT_URGENCY = os.getenv('SERVICENOW_INCIDENT_DEFAULT_URGENCY')

# global variables
polled_APClient = False
polled_APBandwidth = False
polled_Client = False

def get_all_orgs():
    all_orgs = meraki_api('GET', '/organizations')
    orgs = json.loads(all_orgs.text)
    return orgs

def get_all_aps():
    orgs = get_all_orgs()
    macs = []
    names = []
    serials = []
    for org in orgs:
        try:
            org_id = org['id']
            devices = meraki_api('GET', f'/organizations/{org_id}/devices')
            if devices.status_code == 200:
                devices = json.loads(devices.text)
                for device in devices:
                    if "MR" in device['model']:
                        macs.append(device['mac'])
                        names.append(device['name'])
                        serials.append(device['serial'])
        except Exception as e:
            print(f"An error has errored during getting AP from {org['name']}. Error: {e}")
    return [names, macs, serials]

def poll_ap_status():
    orgs = get_all_orgs()
    aps = get_all_aps()

    print("Start polling AP Status...")
    down_aps = dict()
    while True:
        try:
            for org in orgs:
                org_id = org['id']
                device_statuses = meraki_api('GET', f'/organizations/{org_id}/devices/statuses')
                if device_statuses.status_code == 200:
                    device_statuses = json.loads(device_statuses.text)
                    for device_status in device_statuses:
                        if device_status['mac'] in aps[1]:
                            ap_name = device_status['name']
                            ap_status = device_status['status']
                            if device_status['status'] == "online":
                                if device_status['mac'] in down_aps:
                                    new_APStatus = APStatus(name=device_status['name'], mac=device_status['mac'], start_time=down_aps[device_status['mac']], end_time=datetime.now())
                                    db.session.add(new_APStatus)
                                    db.session.commit()
                                    del down_aps[device_status['mac']]
                            if device_status['status'] == "offline":
                                if device_status['mac'] not in down_aps:
                                    down_aps[device_status['mac']] = datetime.now()
                            #print(f"AP name: {ap_name}\nAP Status: {ap_status}")
                            #print(f"Down APs: {down_aps}")
        except Exception as e:
            print(f"An error has errored during AP status polling. Error: {e}")

        time.sleep(int(AP_STATUS_POLLING_INTERVAL))

def poll_ap_client():
    global polled_APClient
    aps = get_all_aps()
    names = aps[0]
    macs = aps[1]
    serials = aps[2]
    print("Start polling AP Client...")
    while True:
        try:
            for i in range(len(serials)):
                payload = {
                    "timespan": int(AP_CLIENT_POLLING_INTERVAL),
                    "resolution": int(AP_CLIENT_POLLING_INTERVAL)
                }
                get_clients = meraki_api('GET', f'/devices/{serials[i]}/clients', payload)
                if get_clients.status_code == 200:
                    get_clients = json.loads(get_clients.text)
                    if len(get_clients) >= int(CLIENT_COUNT_THRESHOLD):
                        alert = True
                    else:
                        alert = False

                    check_APClient = APClient.query.filter_by(mac=macs[i])
                    if check_APClient.count() == 0:
                        new_APClient = APClient(name=names[i], mac=macs[i], count=len(get_clients), alert=alert)
                        db.session.add(new_APClient)
                    else:
                        check_APClient.first().count = len(get_clients)
                        check_APClient.first().alert = alert
                    db.session.commit()
        except Exception as e:
            print(f"An error has errored during AP client polling. Error: {e}")

        polled_APClient = True
        time.sleep(int(AP_CLIENT_POLLING_INTERVAL))

def poll_ap_bandwidth():
    global polled_APBandwidth
    aps = get_all_aps()
    names = aps[0]
    macs = aps[1]
    serials = aps[2]
    print("Start polling AP Bandwidth...")
    while True:
        try:
            for i in range(len(serials)):
                get_device = meraki_api('GET', f'/devices/{serials[i]}')
                get_device = json.loads(get_device.text)
                payload = {
                    "timespan": int(AP_BANDWIDTH_POLLING_INTERVAL),
                    "resolution": int(AP_BANDWIDTH_POLLING_INTERVAL),
                    "deviceSerial": serials[i]
                }
                net_id = get_device['networkId']
                get_usage = meraki_api('GET', f'/networks/{net_id}/wireless/usageHistory', payload)
                if get_usage.status_code == 200:
                    get_usage = json.loads(get_usage.text)
                    if get_usage[0]['totalKbps'] == None:
                        get_usage[0]['totalKbps'] = 0
                    if get_usage[0]['totalKbps'] >= int(BANDWIDTH_THRESHOLD):
                        alert = True
                    else:
                        alert = False

                    check_APBandwidth = APBandwidth.query.filter_by(mac=macs[i])
                    if check_APBandwidth.count() == 0:
                        new_APBandwidth = APBandwidth(name=names[i], mac=macs[i], bandwidth=get_usage[0]['totalKbps'], alert=alert)
                        db.session.add(new_APBandwidth)
                    else:
                        check_APBandwidth.first().bandwidth = get_usage[0]['totalKbps']
                        check_APBandwidth.first().alert = alert
                    db.session.commit()
        except Exception as e:
            print(f"An error has errored during AP bandwidth polling. Error: {e}")

        polled_APBandwidth = True
        time.sleep(int(AP_BANDWIDTH_POLLING_INTERVAL))

def poll_client_performance():
    global polled_Client
    orgs = get_all_orgs()
    print("Start polling Client performance...")
    while True:
        try:
            ap_clients = dict()
            for org in orgs:
                org_id = org['id']
                networks = meraki_api('GET', f'/organizations/{org_id}/networks')
                if networks.status_code == 200:
                    networks = json.loads(networks.text)
                    for network in networks:
                        net_id = network['id']
                        clients = meraki_api('GET', f'/networks/{net_id}/clients')
                        if clients.status_code == 200:
                            clients = json.loads(clients.text)
                            for client in clients:
                                if not client['ssid'] == None and client['status'] == "Online":
                                    client_id = client['id']
                                    payload = {
                                        "timespan": int(CLIENT_PERFORMANCE_POLLING_INTERVAL),
                                        "resolution": int(CLIENT_PERFORMANCE_POLLING_INTERVAL),
                                        "clientId": client_id
                                    }
                                    get_signal = meraki_api('GET', f'/networks/{net_id}/wireless/signalQualityHistory', payload)
                                    if get_signal.status_code == 200:
                                        get_signal = json.loads(get_signal.text)
                                        ap_clients[client['mac']] = {
                                            "id": client['id'],
                                            "name": client['description'],
                                            "ip": client['ip'],
                                            "ap": client['recentDeviceName'],
                                            "ssid": client['ssid'],
                                            "snr": get_signal[0]['snr'],
                                            "rssi": get_signal[0]['rssi']
                                        }
            clients = Client.query.all()
            for client in clients:
                if client.mac not in ap_clients:
                    if client.vip == True:
                        client.ip = None
                        client.ap = None
                        client.ssid = None
                        client.snr = None
                        client.rssi = None
                        db.session.commit()
                    else:
                        db.session.delete(client)
                        db.session.commit()
            for key in ap_clients:
                if ap_clients[key]['name'] == None:
                    ap_clients[key]['name'] = ""
                check_client = Client.query.filter_by(mac=key)
                if check_client.count() == 0:
                    new_client = Client(
                        mac = key,
                        name = ap_clients[key]['name'],
                        client_id = ap_clients[key]['id'],
                        ip = ap_clients[key]['ip'],
                        ap = ap_clients[key]['ap'],
                        ssid = ap_clients[key]['ssid'],
                        snr = ap_clients[key]['snr'],
                        rssi = ap_clients[key]['rssi'],
                        vip = False
                    )
                    if ap_clients[key]['rssi'] == None:
                        new_client.alert = False
                    else:
                        if ap_clients[key]['rssi'] <= int(CLIENT_PERFORMANCE_THRESHOLD):
                            new_client.alert = True
                        else:
                            new_client.alert = False
                    db.session.add(new_client)
                else:
                    check_client = check_client.first()
                    check_client.ip = ap_clients[key]['ip']
                    check_client.ap = ap_clients[key]['ap']
                    check_client.ssid = ap_clients[key]['ssid']
                    check_client.snr = ap_clients[key]['snr']
                    check_client.rssi = ap_clients[key]['rssi']
                    if ap_clients[key]['rssi'] == None:
                        check_client.alert = False
                    else:
                        if ap_clients[key]['rssi'] <= int(CLIENT_PERFORMANCE_THRESHOLD):
                            check_client.alert = True
                        else:
                            check_client.alert = False
                db.session.commit()

        except Exception as e:
            print(f"An error has errored during Client performance polling. Error: {e}")

        polled_Client = True
        time.sleep(int(CLIENT_PERFORMANCE_POLLING_INTERVAL))

def alert():
    global polled_APClient
    global polled_APBandwidth
    global polled_Client
    time.sleep(120)
    while True:
        print("Checking for alert...")
        try:
            # sending alert email
            port = 465  # For SSL
            smtp_server = SMTP_SERVER
            sender_email = SENDER_EMAIL
            receiver_email = RECEIVER_EMAIL
            password = EMAIL_PASSWORD
            message = "Subject: Meraki Alert\n\n"

            if polled_APClient == True:
                alert_APClient = APClient.query.filter_by(alert=True)
                if alert_APClient.count() > 0:
                    message += "Alerting AP Client Count:\n\n"
                    for ap_client in alert_APClient:
                        message += f"Name: {ap_client.name}\nMAC Address: {ap_client.mac}\nClient Count: {ap_client.count}\n\n"

            if polled_APBandwidth == True:
                alert_APBandwidth = APBandwidth.query.filter_by(alert=True)
                if alert_APBandwidth.count() > 0:
                    message += "Alerting AP Bandwidth:\n\n"
                    for ap_bandwidth in alert_APBandwidth:
                        message += f"Name: {ap_bandwidth.name}\nMAC Address: {ap_bandwidth.mac}\nUsage: {ap_bandwidth.bandwidth}\n\n"

            if polled_Client == True:
                alert_Client = Client.query.filter_by(alert=True)
                if alert_Client.count() > 0:
                    message += "Alerting Client Performance:\n\n"
                    for client in alert_Client:
                        message += f"Name: {client.name}\nMAC Address: {client.mac}\nIP Address: {client.ip}\nConnected AP: {client.ap}\nSSID: {client.ssid}\nSNR: {client.snr}\nRSSI: {client.rssi}\n\n"

            if polled_APClient or polled_APBandwidth or polled_Client:
                context = ssl.create_default_context()
                with smtplib.SMTP_SSL(smtp_server, port, context=context) as server:
                    server.login(sender_email, password)
                    server.sendmail(sender_email, receiver_email, message)
                    print("Alert email sent")

        except Exception as e:
            print(f"An error has errored during alert checking. Error: {e}")

        try:
            # create ServiceNow incident for alerting VIP Client
            alert_VIPClient = Client.query.filter_by(vip=True, alert=True)
            headers = {
                "Content-Type":"application/json",
                "Accept":"application/json"
            }
            auth = (SERVICENOW_USERNAME, SERVICENOW_PASSWORD)
            for vip_client in alert_VIPClient:
                ticket = {
                    "impact": SERVICENOW_INCIDENT_DEFAULT_IMPACT,
                    "urgency": SERVICENOW_INCIDENT_DEFAULT_URGENCY,
                    "category": "Network",
                    "short_description": f"Alert for VIP Client Performance - {vip_client.name}",
                    "description": f"Name: {client.name}\nMAC Address: {client.mac}\nIP Address: {client.ip}\nConnected AP: {client.ap}\nSSID: {client.ssid}\nSNR: {client.snr}\nRSSI: {client.rssi}"
                }
                ticket_creation = requests.post(SERVICENOW_INSTANCE + "/api/now/table/incident", auth=auth, headers=headers, json=ticket)
                print(json.loads(ticket_creation.text))
                print(f"ServiceNow ticket created for {vip_client.name}")
        except Exception as e:
            print(f"An error has errored during alert checking for VIP Clients. Error: {e}")

        polled_APClient = False
        polled_APBandwidth = False
        polled_Client = False
        time.sleep(300)

