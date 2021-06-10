""" Copyright (c) 2021 Cisco and/or its affiliates.
This software is licensed to you under the terms of the Cisco Sample
Code License, Version 1.1 (the "License"). You may obtain a copy of the
License at
           https://developer.cisco.com/docs/licenses
All use of the material herein must be in accordance with the terms of
the License. All rights not expressly granted by the License are
reserved. Unless required by applicable law or agreed to separately in
writing, software distributed under the License is distributed on an "AS
IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express
or implied.
"""

# Import Section
from flask import Flask, render_template, request, redirect, send_file, Response
from datetime import datetime
import requests
import json
from dotenv import load_dotenv
import os
from io import BytesIO
import time
from models import db, APStatus, System, APClient, APBandwidth, Client
from sqlalchemy_utils import database_exists
from threading import Thread
from poll_ap import poll_ap_status, get_all_aps, poll_ap_client, poll_ap_bandwidth, poll_client_performance, alert
from helper import getSystemTimeAndLocation, meraki_api, time_between
from xlsxwriter.workbook import Workbook

# load all environment variables
load_dotenv()
DB_PATH = os.getenv("DB_PATH")
#MERAKI_SCANNING_VALIDATOR = os.getenv("MERAKI_SCANNING_VALIDATOR")

#Startup functions
def on_startup():
    # start polling AP status
    ap_status_thread = Thread(target=poll_ap_status)
    ap_status_thread.daemon = True
    ap_status_thread.start()

    # start polling AP clients
    ap_client_thread = Thread(target=poll_ap_client)
    ap_client_thread.daemon = True
    ap_client_thread.start()

    # start polling AP bandwidth
    ap_bandwidth_thread = Thread(target=poll_ap_bandwidth)
    ap_bandwidth_thread.daemon = True
    ap_bandwidth_thread.start()

    # start polling Client performance
    client_performance_thread = Thread(target=poll_client_performance)
    client_performance_thread.daemon = True
    client_performance_thread.start()

    # start polling Client performance
    alert_thread = Thread(target=alert)
    alert_thread.daemon = True
    alert_thread.start()

def create_app():
    on_startup()
    return Flask(__name__)

#Flask app
app = create_app()
app.config['SQLALCHEMY_DATABASE_URI'] = DB_PATH
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# initialize DB
db.app = app
db.init_app(app)
if not database_exists(DB_PATH):
    db.create_all()

    # mark date of start using system
    now = datetime.now()
    system_start = datetime.strptime(now.strftime("%Y-%m-%d") + " 00:00:00", "%Y-%m-%d %H:%M:%S")
    system = System(start=system_start)
    db.session.add(system)
    db.session.commit()

##Routes
@app.route('/')
def get_base():
    #try:
        # get Meraki API Key
        #if MERAKI_API_KEY:
        #    headers['X-Cisco-Meraki-API-Key'] = MERAKI_API_KEY
    return redirect('/ap_uptime')

        #Page without error message and defined header links
        #return render_template('login.html', timeAndLocation=getSystemTimeAndLocation())
    #except Exception as e:
    #    print(e)
        #OR the following to show error message
    #    return render_template('login.html', error=True, errormessage=f"Error: {e}", timeAndLocation=getSystemTimeAndLocation())

#@app.route('/', methods=['POST'])
#def post_base():
#    try:
#        if not MERAKI_API_KEY:
#            headers['X-Cisco-Meraki-API-Key'] = request.form.get("key")
#
#        #Page without error message and defined header links
#        return redirect('/ap_uptime')
#    except Exception as e:
#        print(e)
#        #OR the following to show error message
#        return render_template('login.html', error=True, errormessage=f"ERROR: {e}", timeAndLocation=getSystemTimeAndLocation())

@app.route('/ap_uptime')
def get_ap_uptime():
    try:
        system_start = System.query.first()
        system_start = system_start.start

        #Page without error message and defined header links
        return render_template('ap_uptime.html', system_start=system_start.strftime("%Y-%m-%d"), timeAndLocation=getSystemTimeAndLocation())
    except Exception as e:
        print(e)
        #OR the following to show error message
        return render_template('ap_uptime.html', error=True, errormessage=f"Error: {e}", timeAndLocation=getSystemTimeAndLocation())

@app.route('/ap_uptime', methods=['POST'])
def post_ap_uptime():
    try:
        system_start = System.query.first()
        system_start = system_start.start

        data = json.loads(request.form['data'])
        start_time = datetime.strptime(data['start_time'] + " 00:00:00", "%Y-%m-%d %H:%M:%S")
        end_time = datetime.strptime(data['end_time'] + " 23:59:59", "%Y-%m-%d %H:%M:%S")

        # date validation
        if start_time < system_start:
            return f"Error: Start Date must be greater than system start date"
        if end_time < start_time:
            return f"Error: End Date must be greater than Start Date"

        # selected time range
        time_range = time_between(start_time, end_time)

        # add down APs data
        data_in_range = APStatus.query.filter(APStatus.start_time >= start_time, APStatus.end_time <= end_time).all()
        data_by_ap = dict()
        for ap in data_in_range:
            if ap.mac not in data_by_ap:
                data_by_ap[ap.mac] = dict()
                data_by_ap[ap.mac]['occurence'] = 0
                data_by_ap[ap.mac]['total_down'] = 0
            data_by_ap[ap.mac]['name'] = ap.name
            data_by_ap[ap.mac]['occurence'] += 1
            data_by_ap[ap.mac]['total_down'] += time_between(ap.start_time, ap.end_time)

        for key in data_by_ap:
            data_by_ap[key]['uptime'] = str(round((1 - data_by_ap[key]['total_down'] / time_range) * 100, 4))

        # add healthy APs
        aps = get_all_aps()
        for i in range(len(aps[0])):
            if aps[1][i] not in data_by_ap:
                data_by_ap[aps[1][i]] = dict()
                data_by_ap[aps[1][i]]['name'] = aps[0][i]
                data_by_ap[aps[1][i]]['occurence'] = 0
                data_by_ap[aps[1][i]]['uptime'] = 100

        return json.dumps(data_by_ap)
    except Exception as e:
        print(e)
        return "Error: Unexpected error"

@app.route('/download_records', methods=['POST'])
def download_records():
    try:
        data = request.get_json()
        start_time = datetime.strptime(data['start_time'] + " 00:00:00", "%Y-%m-%d %H:%M:%S")
        end_time = datetime.strptime(data['end_time'] + " 23:59:59", "%Y-%m-%d %H:%M:%S")
        data_in_range = APStatus.query.filter(APStatus.start_time >= start_time, APStatus.end_time <= end_time).all()

        # selected time range
        time_range = time_between(start_time, end_time)

        # add down APs data
        data_in_range = APStatus.query.filter(APStatus.start_time >= start_time, APStatus.end_time <= end_time).all()
        data_by_ap = dict()
        for ap in data_in_range:
            if ap.mac not in data_by_ap:
                data_by_ap[ap.mac] = dict()
                data_by_ap[ap.mac]['occurence'] = 0
                data_by_ap[ap.mac]['total_down'] = 0
            data_by_ap[ap.mac]['name'] = ap.name
            data_by_ap[ap.mac]['occurence'] += 1
            data_by_ap[ap.mac]['total_down'] += time_between(ap.start_time, ap.end_time)

        for key in data_by_ap:
            data_by_ap[key]['uptime'] = str(round((1 - data_by_ap[key]['total_down'] / time_range) * 100, 4))

        # add healthy APs
        aps = get_all_aps()
        for i in range(len(aps[0])):
            if aps[1][i] not in data_by_ap:
                data_by_ap[aps[1][i]] = dict()
                data_by_ap[aps[1][i]]['name'] = aps[0][i]
                data_by_ap[aps[1][i]]['occurence'] = 0
                data_by_ap[aps[1][i]]['uptime'] = 100

        output = BytesIO()
        book = Workbook(output)

        ap_uptime_percentage = book.add_worksheet("AP Uptime Percentage")
        ap_uptime_percentage.write(0, 0, "AP Name")
        ap_uptime_percentage.write(0, 1, "MAC Address")
        ap_uptime_percentage.write(0, 2, "Outage Occurrence")
        ap_uptime_percentage.write(0, 3, "Uptime Percentage")
        row = 1
        for ap in data_by_ap:
            ap_uptime_percentage.write(row, 0, data_by_ap[ap]['name'])
            ap_uptime_percentage.write(row, 1, ap)
            ap_uptime_percentage.write(row, 2, data_by_ap[ap]['occurence'])
            ap_uptime_percentage.write(row, 3, f"{data_by_ap[ap]['uptime']}%")
            row += 1

        downtime_log = book.add_worksheet("Downtime Log")
        downtime_log.write(0, 0, "AP Name")
        downtime_log.write(0, 1, "MAC Address")
        downtime_log.write(0, 2, "Start Time")
        downtime_log.write(0, 3, "End Time")
        row = 1
        for ap in data_in_range:
            downtime_log.write(row, 0, ap.name)
            downtime_log.write(row, 1, ap.mac)
            downtime_log.write(row, 2, ap.start_time.strftime("%Y-%m-%d %H:%M:%S"))
            downtime_log.write(row, 3, ap.end_time.strftime("%Y-%m-%d %H:%M:%S"))
            row += 1

        book.close()
        output.seek(0)

        return send_file(output,
                         attachment_filename=f"AP_Uptime_Report_{data['start_time']}_to_{data['end_time']}.xlsx",
                         as_attachment=True,
                         mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    except Exception as e:
        print(e)
        return "Error: Unexpected error"

@app.route('/vip_client')
def get_vip_client():
    try:
        vip_clients = Client.query.filter_by(vip=True)

        #Page without error message and defined header links
        return render_template('vip_client.html', vip_clients=vip_clients, timeAndLocation=getSystemTimeAndLocation())
    except Exception as e:
        print(e)
        #OR the following to show error message
        return render_template('vip_client.html', error=True, errormessage=f"Error: {e}", timeAndLocation=getSystemTimeAndLocation())

@app.route('/vip_client', methods=['POST'])
def post_vip_client():
    try:
        data = json.loads(request.form['data'])
        client_name = data['client_name']
        client_mac = data['client_mac'].lower()
        action = data['action']

        if action == "ADD":
            check_VIPClient = Client.query.filter_by(mac=client_mac)
            if check_VIPClient.count() == 0:
                new_VIPClient = Client(mac=client_mac, name=client_name, vip=True, alert=False)
                db.session.add(new_VIPClient)
            else:
                check_VIPClient.first().name = client_name
                check_VIPClient.first().vip = True
            db.session.commit()
            return "Y"
        elif action == "DELETE":
            delete_VIPClient = Client.query.filter_by(mac=client_mac).first()
            delete_VIPClient.vip = False
            db.session.commit()
            return "Y"
    except Exception as e:
        print(e)
        return f"Error: {e}"

@app.route('/client_performance')
def get_client_performance():
    try:
        clients = Client.query.all()

        #Page without error message and defined header links
        return render_template('client_performance.html', clients=clients, timeAndLocation=getSystemTimeAndLocation())
    except Exception as e:
        print(e)
        #OR the following to show error message
        return render_template('client_performance.html', error=True, errormessage=f"Error: {e}", timeAndLocation=getSystemTimeAndLocation())

#@app.route('/scanning')
#def get_scanning():
#    return MERAKI_SCANNING_VALIDATOR

#@app.route('/scanning', methods=['POST'])
#def post_scanning():
#    data = request.json
#    print(data)
#    return Response(status=200)

@app.route('/client_count')
def get_client_count():
    try:
        aps_clients = APClient.query.all()

        #Page without error message and defined header links
        return render_template('client_count.html', aps_clients=aps_clients, timeAndLocation=getSystemTimeAndLocation())
    except Exception as e:
        print(e)
        #OR the following to show error message
        return render_template('client_count.html', error=True, errormessage=f"Error: {e}", timeAndLocation=getSystemTimeAndLocation())

@app.route('/bandwidth')
def get_bandwidth():
    try:
        aps_bandwidth = APBandwidth.query.all()

        #Page without error message and defined header links
        return render_template('bandwidth.html', aps_bandwidth=aps_bandwidth, timeAndLocation=getSystemTimeAndLocation())
    except Exception as e:
        print(e)
        #OR the following to show error message
        return render_template('bandwidth.html', error=True, errormessage=f"Error: {e}", timeAndLocation=getSystemTimeAndLocation())


#Main Function
if __name__ == "__main__":
    app.run(host='0.0.0.0', debug=True)

