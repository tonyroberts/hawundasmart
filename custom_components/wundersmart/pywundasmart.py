import asyncio
import time
import aiohttp
import xmltodict
import hmac
import hashlib
import xmltodict
import base64

DEVICE_DEFS = {'device_sn', 'prod_sn', 'device_name', 'device_type', 'eth_mac', 'name', 'id', 'i'}


async def get_devices(httpsession: aiohttp.ClientSession, wunda_ip, wunda_user, wunda_pass):
    """ Returns a list of active devices connected to the Wundasmart controller """

    devices = {}

    # Query the cmd API, which returns a list of rooms configured on the controller. Data is formatted in JSON
    wunda_url = f"http://{wunda_ip}/cmd.cgi"
    try:
        async with httpsession.get(wunda_url, auth=aiohttp.BasicAuth(wunda_user, wunda_pass)) as resp:
            status = resp.status

            if status == 200:
                data = await resp.json()
                for room in data["rooms"]:
                    room_id = str(room["i"])
                    device = devices.setdefault(room_id, {"device_type": "ROOM"})
                    state = device.setdefault("state", {})
                    device.update({k: v for k, v in room.items() if k in DEVICE_DEFS})
                    state.update({k: v for k, v in room.items() if k not in DEVICE_DEFS})
            else:
                return {"state": False, "code": status}
    except (asyncio.TimeoutError, aiohttp.ClientError):
        return {"state": False, "code": 500}

    # Query the syncvalues API, which returns a list of all sensor values for all devices. Data is formatted as semicolon-separated k;v pairs
    wunda_url = f"http://{wunda_ip}/syncvalues.cgi?v=2"
    try:
        async with httpsession.get(wunda_url, auth=aiohttp.BasicAuth(wunda_user, wunda_pass)) as resp:
            status = resp.status
            if status == 200:
                data = await resp.text()
                for device_state in data.splitlines():
                    device_values = dict(x.split(":") for x in device_state.split(";") if ":" in x)
                    device_id = str(device_state.split(";")[0])

                    device = devices.setdefault(device_id, {})
                    state = device.setdefault("state", {})

                    device.update({k: v for k, v in device_values.items() if k in DEVICE_DEFS})
                    state.update({k: v for k, v in device_values.items() if k not in DEVICE_DEFS})
            else:
                return {"state": False, "code": status}
    except (asyncio.TimeoutError, aiohttp.ClientError):
        return {"state": False, "code": 500, "message": "HTTP client error"}

    # Give each device a unique id based on wunda id and device type
    for device_id, device in devices.items():
        device_type = device.get("device_type", "unknown")
        device["id"] = f"{device_type}.{device_id}"

    return {"state": True, "devices": devices}


async def put_state(httpsession, wunda_ip, wunda_user, wunda_pass, wunda_id, wunda_key, wunda_val):
    response = {}
    wunda_url = f"http://{wunda_ip}/setregister.cgi"
    try:
        params = f"{wunda_id}@{wunda_key}={wunda_val}"
        async with httpsession.get(wunda_url, auth=aiohttp.BasicAuth(wunda_user, wunda_pass), params=params) as resp:
            status = resp.status
            if status == 200:
                # the setregister.cgi API returns XML formatted response, e.g. <cmd status="ok"><device id="0"><reg vid="121" tid="temp_pre" v="1" status="ok"/></device></cmd>
                xml_data = await resp.text()
                xml_dict = xmltodict.parse(xml_data, attr_prefix='')
                if xml_dict["cmd"]["status"] == "ok":
                    if xml_dict["cmd"]["device"]["reg"]["status"] == "ok":
                        response[xml_dict["cmd"]["device"]["reg"]["tid"]] = xml_dict["cmd"]["device"]["reg"]["v"]
                    else:
                        return {"state": False, "code": 500, "message": xml_dict["cmd"]["device"]["reg"]["status"]}
                else:
                    return {"state": False, "code": 500, "message": xml_dict["cmd"]["status"]}
            else:
                return {"state": False, "code": status}
    except (asyncio.TimeoutError, aiohttp.ClientError):
        return {"state": False, "code": 500, "message": "HTTP client error"}

    return {"state": True, "response": response}


async def get_credentials(wunda_user, wunda_pass):
    response = {}
    wunda_session = aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=True))
    curtime = str(round(time.time())+3600)
    salt = "43785hf284hdf3"
    key = salt+wunda_pass
    keyHmacSha512 = hmac.new(hashlib.sha512(str(key).encode()).digest(), curtime.encode(), hashlib.sha512).hexdigest()
    url = "https://wunda.azurewebsites.net/api/1.1/?login"
    formdata = aiohttp.FormData( {'user': wunda_user, 'hash': keyHmacSha512, 'time': curtime} )
    resp = await wunda_session.post(url, data=formdata)
    status = resp.status
    if status == 200:
        if resp.headers["api-status"] == 'ok':
            resp = await wunda_session.post("https://wunda.azurewebsites.net/api/1.1/?devicelist")
            if status == 200:
                if resp.headers["api-status"] == 'ok':
                    xml_data = await resp.text()
                    xml_dict = xmltodict.parse(xml_data, attr_prefix='')
                    device_id = xml_dict["api"]["response"]["device"]["id"]
                    resp = await wunda_session.post("https://wunda.azurewebsites.net/api/1.1/?id=5056&query=getregister.cgi?0%40auth_root%260%40eth_ip_ro")
                    if status == 200:
                        if resp.headers["api-status"] == 'ok':
                            xml_data = await resp.text()
                            xml_dict = xmltodict.parse(xml_data, attr_prefix='')
                            for tid in xml_dict["cmd"]["device"]["reg"]:
                                response[tid["tid"]] = tid["v"]
                            (local_user,local_pass) = str(base64.b64decode(response["auth_root"])).split(":")
                            local_pass = local_pass[:-1]
                            local_user = local_user[2:]
                        else:
                            return {"state": False, "code": 500, "message": resp.headers["api-status-msg"]}
                    else:
                        return {"state": False, "code": status}
                else:
                    return {"state": False, "code": 500, "message": resp.headers["api-status-msg"]}
            else:
                return {"state": False, "code": status}
        else:
            return {"state": False, "code": 500, "message": resp.headers["api-status-msg"]}
    else:
        return {"state": False, "code": status}

    await wunda_session.close()

    response["user"] = local_user
    response["pass"] = local_pass

    return response
