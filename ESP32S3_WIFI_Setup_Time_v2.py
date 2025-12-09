try:
    import ntptime
    NTPTIME_AVAILABLE = True
except ImportError:
    print("警告: ntptime 模块不可用。时间同步功能将被禁用。")
    NTPTIME_AVAILABLE = False

import network
import socket
import time
import json
import machine

AP_SSID = "ESP32_Setup"
AP_PASSWORD = "12345678"
AP_AUTHMODE = network.AUTH_WPA_WPA2_PSK
WEB_PORT = 80
WIFI_CONNECT_TIMEOUT = 30

DAYS_IN_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

g_ap_interface = None

def is_leap_year(year):
    return (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0)

def set_time():
    if not NTPTIME_AVAILABLE:
        print("时间同步失败：ntptime 模块不可用。")
        return
    
    print("正在同步NTP时间...")

    servers_to_try = ["pool.ntp.org", "ntp.aliyun.com", "cn.pool.ntp.org"]

    for host in servers_to_try:
        try:
            print(f"尝试 NTP 服务器: {host}")
            
            if hasattr(ntptime, 'host'):
                original_host = getattr(ntptime, 'host', None)
                ntptime.host = host

            ntp_timestamp = ntptime.time()
            print(f"NTP时间同步成功 (使用服务器 {host})。获取到的 Unix 时间戳 (1970-based): {ntp_timestamp}")

            utc_tm_tuple = time.gmtime(ntp_timestamp)
            print(f"使用 gmtime 解析的 UTC 时间元组 (1970-based): {utc_tm_tuple}")

            year_1970_based = utc_tm_tuple[0]
            adjusted_year_for_rtc = year_1970_based - 2000
            
            if adjusted_year_for_rtc < 0 or adjusted_year_for_rtc > 255:
                 raise ValueError(f"调整后的年份 {year_1970_based} ({adjusted_year_for_rtc} for RTC) 超出 ESP32 RTC 支持范围 (0-255)。")

            rtc_datetime_tuple = (
                adjusted_year_for_rtc,
                utc_tm_tuple[1],
                utc_tm_tuple[2],
                utc_tm_tuple[6],
                utc_tm_tuple[3],
                utc_tm_tuple[4],
                utc_tm_tuple[5],
                0
            )
            print(f"准备设置的 RTC 8元组 (年份已调整为相对于 2000): {rtc_datetime_tuple}")

            rtc = machine.RTC()
            rtc_before = rtc.datetime()
            print(f"设置 RTC 前读取到的时间: {rtc_before}")

            rtc.datetime(rtc_datetime_tuple)
            print("RTC 已手动设置为准确的 UTC 时间 (年份已按 ESP32 内部纪元调整)。")

            rtc_after = rtc.datetime()
            print(f"设置 RTC 后读取到的时间: {rtc_after}")

            final_timestamp = time.time()
            print(f"设置后再次读取 time.time() (应为 1970-based): {final_timestamp}")
            print(f"time.time() 差值 (应接近0): {final_timestamp - ntp_timestamp}")

            if hasattr(ntptime, 'host') and original_host is not None:
                ntptime.host = original_host

            return

        except (AttributeError, ValueError) as specific_error:
             print(f"使用 NTP 服务器 {host} 时出现特定错误: {specific_error}")
             if hasattr(ntptime, 'host') and original_host is not None:
                 try:
                     ntptime.host = original_host
                 except:
                     pass
             continue

        except Exception as e1:
            print(f"使用 NTP 服务器 {host} 同步或设置时间时出错: {e1}")
            if hasattr(ntptime, 'host') and original_host is not None:
                try:
                    ntptime.host = original_host
                except:
                    pass
            continue

    print("警告：所有 NTP 时间同步尝试均失败。设备时间可能不准确。")
    print("常见原因：未连接到互联网，或防火墙阻止了UDP端口123。")


def get_beijing_time_tuple():
    rtc = machine.RTC()
    rtc_tuple = rtc.datetime()
    year_adjusted_back = rtc_tuple[0] + 2000
    return (year_adjusted_back, rtc_tuple[1], rtc_tuple[2], rtc_tuple[4], rtc_tuple[5], rtc_tuple[6])

def get_beijing_timestamp():
    try:
        rtc = machine.RTC()
        rtc_tuple = rtc.datetime()
        year = rtc_tuple[0] + 2000
        month = rtc_tuple[1]
        day = rtc_tuple[2]
        hour = rtc_tuple[4]
        minute = rtc_tuple[5]
        second = rtc_tuple[6]

        days = 0
        for y in range(1970, year):
            if is_leap_year(y):
                days += 366
            else:
                days += 365

        for m in range(1, month):
            days += DAYS_IN_MONTH[m - 1]
            if m == 2 and is_leap_year(year):
                days += 1

        days += day - 1

        timestamp = days * 24 * 3600 + hour * 3600 + minute * 60 + second + (8 * 3600)
        return timestamp
    except Exception as e:
        print(f"计算时间戳时出错: {e}")
        return 0

def format_time(tm_tuple):
    year, month, day, hour, minute, second = tm_tuple[:6]
    return "{:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}".format(year, month, day, hour, minute, second)


def start_ap(ssid, password):
    global g_ap_interface
    print(f"正在启动/重启 SoftAP '{ssid}'...")
    sta_if = network.WLAN(network.STA_IF)
    if sta_if.active():
        print("启动 AP 前停用 STA 接口...")
        sta_if.disconnect()
        sta_if.active(False)
        time.sleep(1)

    if g_ap_interface is None:
        print("初始化 AP 接口...")
        g_ap_interface = network.WLAN(network.AP_IF)
    ap = g_ap_interface

    try:
        if ap.active():
            print("停用现有 AP...")
            ap.active(False)
            time.sleep(0.5)

        print("配置 AP 参数...")
        ap.config(essid=ssid, authmode=AP_AUTHMODE, password=password)
        print("激活 AP 接口...")
        ap.active(True)

    except Exception as e:
        print(f"配置/激活 AP 时出错: {e}。")
        try:
            print("尝试回退到开放网络配置...")
            ap.config(essid=ssid)
            ap.active(True)
        except Exception as e2:
            print(f"回退启动 AP 也失败了: {e2}")
        return None, None

    print("等待 AP 激活...")
    timeout = 10
    while not ap.active() and timeout > 0:
        time.sleep(0.5)
        timeout -= 1
        print(".", end='')
        
    if ap.active():
        ip_address = ap.ifconfig()[0]
        print(f"\nSoftAP '{ssid}' 已激活。IP 地址: {ip_address}")
        return ap, ip_address
    else:
        print("\n多次尝试后仍未成功启动/重启 SoftAP。")
        return None, None


def scan_wifi_networks():
    print("正在扫描 WiFi 网络...")
    sta_if = network.WLAN(network.STA_IF)
    was_active = sta_if.active()
    if not was_active:
        sta_if.active(True)
        time.sleep(1)
        
    try:
        nets = sta_if.scan()
        ssids = []
        for net in nets:
            ssid_bytes = net[0]
            try:
                ssid_str = ssid_bytes.decode('utf-8')
                if ssid_str:
                    ssids.append(ssid_str)
            except UnicodeDecodeError:
                print(f"跳过具有非 UTF-8 SSID 的网络: {ssid_bytes}")
                pass
                
        unique_ssids = sorted(list(set(ssids)))
        print(f"扫描完成。找到 {len(unique_ssids)} 个唯一网络。")
        return unique_ssids
    except Exception as e:
        print(f"WiFi 扫描期间出错: {e}")
        return []
    finally:
        if not was_active:
            sta_if.active(False)


def simple_unquote(s):
    if '%' not in s and '+' not in s:
        return s
    res = ''
    i = 0
    while i < len(s):
        if s[i] == '%':
            try:
                hex_val = s[i+1:i+3]
                char_val = int(hex_val, 16)
                res += chr(char_val)
                i += 3
            except (ValueError, IndexError):
                res += s[i]
                i += 1
        elif s[i] == '+':
            res += ' '
            i += 1
        else:
            res += s[i]
            i += 1
    return res

def parse_form_data(encoded_data):
    data = {}
    pairs = encoded_data.replace('+', ' ').split('&')
    for pair in pairs:
        if '=' in pair:
            key, value = pair.split('=', 1)
            key_decoded = simple_unquote(key)
            value_decoded = simple_unquote(value)
            data[key_decoded] = value_decoded
    return data


def generate_initial_html(error_msg="", pre_selected_ssid=""):
    pre_selected_ssid_str = str(pre_selected_ssid) if pre_selected_ssid is not None else ""
    
    error_div = f'<div id="error-message" style="color:red; background-color: #ffebee; padding: 10px; border-radius: 4px; margin-bottom: 15px;">{error_msg}</div>' if error_msg else ""
    
    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <title>ESP32 WiFi 配置</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {{
            font-family: Arial, sans-serif;
            padding: 15px;
            margin: 0;
            background-color: #f4f4f4;
        }}
        h1 {{
            color: #333;
        }}
        #scan-connect-section {{
            background-color: #fff;
            padding: 15px;
            border-radius: 4px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        label {{
            display: block;
            margin-bottom: 5px;
            font-weight: bold;
        }}
        input[type="password"], select {{
            width: 100%;
            padding: 10px;
            margin-bottom: 15px;
            border: 1px solid #ccc;
            border-radius: 4px;
            box-sizing: border-box;
        }}
        button {{
            background-color: #2196F3;
            color: white;
            padding: 12px 20px;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            width: 100%;
            font-size: 16px;
        }}
        button:hover {{
            background-color: #1976D2;
        }}
        ul {{
            list-style-type: none;
            padding: 0;
        }}
        li {{
            padding: 8px 0;
            border-bottom: 1px solid #eee;
        }}
        #status {{
            margin-top: 10px;
            font-style: italic;
            color: #666;
        }}

        @media screen and (min-width: 600px) {{
            body {{
                padding: 20px;
            }}
            #scan-connect-section {{
                max-width: 600px;
                margin: 0 auto 15px auto;
            }}
        }}
    </style>
</head>
<body>
    <h1>ESP32 WiFi 配置</h1>

    {error_div}

    <div id="scan-connect-section">
        <h3>正在扫描网络...</h3>
        <form id="wifi-form">
            <label for="ssid-select">选择网络:</label>
            <select name="ssid" id="ssid-select">
                <option value="">-- 请选择 --</option>
            </select><br><br>

            <div id="password-field" style="display:none;">
                <label for="password-input">密码:</label>
                <input type="password" name="password" id="password-input"><br><br>
            </div>

            <button type="submit">连接</button>
        </form>
        <div id="status">正在连接网络...</div>
        <ul id="network-list"></ul>
    </div>

    <script>
        let networks = [];

        function updateNetworkList() {{
            const listElement = document.getElementById('network-list');
            const selectElement = document.getElementById('ssid-select');

            listElement.innerHTML = '';
            selectElement.innerHTML = '<option value="">-- 请选择 --</option>';

            networks.forEach(net => {{
                const li = document.createElement('li');
                li.textContent = net;
                listElement.appendChild(li);

                const option = document.createElement('option');
                option.value = net;
                option.textContent = net;

                if (net === "{pre_selected_ssid_str}") {{
                    option.selected = true;
                }}
                selectElement.appendChild(option);
            }});
        }}

        function scanNetworks() {{
            fetch('/scan')
                .then(response => response.json())
                .then(data => {{
                    networks = data.networks || [];
                    updateNetworkList();
                    document.querySelector('h3').textContent = '可用网络:';
                }})
                .catch(error => {{
                    console.error('扫描失败:', error);
                    document.querySelector('h3').textContent = '扫描失败，请刷新页面重试。';
                }});
        }}

        document.addEventListener('DOMContentLoaded', () => {{
            scanNetworks();

            document.getElementById('ssid-select').addEventListener('change', (event) => {{
                const selectedSSID = event.target.value;
                const passwordField = document.getElementById('password-field');
                if (selectedSSID) {{
                    passwordField.style.display = 'block';
                }} else {{
                    passwordField.style.display = 'none';
                }}
            }});

            document.getElementById('wifi-form').addEventListener('submit', (event) => {{
                event.preventDefault();

                const formData = new FormData(event.target);
                const ssid = formData.get('ssid');
                const password = formData.get('password');

                if (!ssid) {{
                    alert('请选择一个网络。');
                    return;
                }}

                document.getElementById('status').textContent = `正在连接到 ${{ssid}}...`;

                fetch('/configure', {{
                    method: 'POST',
                    body: new URLSearchParams(formData),
                    headers: {{
                        'Content-Type': 'application/x-www-form-urlencoded',
                    }},
                }})
                .then(response => {{
                    if (response.ok || response.status === 500) {{
                        return response.text();
                    }} else {{
                        throw new Error(`HTTP error! Status: ${{response.status}}`);
                    }}
                }})
                .then(html => {{
                    document.open();
                    document.write(html);
                    document.close();
                }})
                .catch(error => {{
                    console.error('连接请求失败:', error);
                    document.getElementById('status').textContent = '连接请求发送失败。';
                }});
            }});
        }});
    </script>
</body>
</html>"""
    return html_content

def generate_success_html(device_ip):

    rtc = machine.RTC()
    rtc_time = rtc.datetime()
    year = rtc_time[0] + 2000
    month = rtc_time[1]
    day = rtc_time[2]
    hour = rtc_time[4]
    minute = rtc_time[5]
    second = rtc_time[6]
    
    beijing_hour = (hour + 8) % 24
    beijing_day = day
    if hour + 8 >= 24:
        beijing_day += 1
        
    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <title>ESP32 WiFi 配置 - 成功</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {{
            font-family: Arial, sans-serif;
            padding: 15px;
            margin: 0;
            background-color: #f4f4f4;
        }}
        #success-section {{
            background-color: #e8f5e9;
            padding: 15px;
            border-radius: 4px;
            margin-bottom: 15px;
            text-align: center;
        }}
        #time-display {{
            font-family: monospace;
        }}
        a {{
            display: inline-block;
            margin-top: 10px;
            color: #2196F3;
            text-decoration: none;
        }}
        a:hover {{
            text-decoration: underline;
        }}

        @media screen and (min-width: 600px) {{
            body {{
                padding: 20px;
            }}
            #success-section {{
                max-width: 600px;
                margin: 0 auto 15px auto;
            }}
        }}
    </style>
</head>
<body>
    <div id="success-section">
        <h2>成功!</h2>
        <p>已成功连接到 WiFi 网络。</p>
        <p>您的 ESP32 新 IP 地址是: <strong>{device_ip}</strong></p>
        <p>当前北京时间是: <strong id='time-display'>{year:04d}-{month:02d}-{day:02d} {beijing_hour:02d}:{minute:02d}:{second:02d}</strong></p>
        <a href="/">返回网络选择</a>
    </div>

    <script>
        // 使用服务器时间作为基准
        function padZero(num) {{
            return num.toString().padStart(2, '0');
        }}

        // 获取服务器时间作为基准
        const serverYear = {year};
        const serverMonth = {month};
        const serverDay = {day};
        const serverHour = {beijing_hour};
        const serverMinute = {minute};
        const serverSecond = {second};

        // 计算服务器时间戳（北京时间）
        const serverDate = new Date(serverYear, serverMonth - 1, serverDay, serverHour, serverMinute, serverSecond);
        const serverTimestamp = serverDate.getTime();

        function updateTimeDisplay() {{
            try {{
                // 获取当前时间并计算偏移
                const now = new Date();
                const elapsedMs = now.getTime() - serverTimestamp;
                
                // 计算当前时间
                const currentDate = new Date(serverDate.getTime() + elapsedMs);

                const year = currentDate.getFullYear();
                const month = padZero(currentDate.getMonth() + 1);
                const day = padZero(currentDate.getDate());
                const hours = padZero(currentDate.getHours());
                const minutes = padZero(currentDate.getMinutes());
                const seconds = padZero(currentDate.getSeconds());

                const formattedTime = `${{year}}-${{month}}-${{day}} ${{hours}}:${{minutes}}:${{seconds}}`;
                document.getElementById('time-display').textContent = formattedTime;
            }} catch (err) {{
                console.error("更新时间显示时出错:", err);
                document.getElementById('time-display').textContent = "时间获取失败";
            }}
        }}

        // 立即更新一次
        updateTimeDisplay();
        
        // 每秒更新一次时间显示
        setInterval(updateTimeDisplay, 1000);
    </script>
</body>
</html>"""
    return html_content

def generate_error_html(message, pre_selected_ssid=""):
    pre_selected_ssid_str = str(pre_selected_ssid) if pre_selected_ssid is not None else ""
    return generate_initial_html(error_msg=message, pre_selected_ssid=pre_selected_ssid)

def recv_all(client_socket, length):
    data = b''
    while len(data) < length:
        try:
            packet = client_socket.recv(length - len(data))
            if not packet:
                return None
            data += packet
        except OSError as e:
            return None
    return data

def attempt_wifi_connection(ssid, password):
    print(f"正在尝试连接到 WiFi: '{ssid}'...")
    print("激活 STA 接口...")
    sta_if = network.WLAN(network.STA_IF)
    if not sta_if.active():
        sta_if.active(True)
        time.sleep(1)

    if sta_if.isconnected():
        print("断开之前的网络连接...")
        sta_if.disconnect()
        time.sleep(1)

    print("开始连接...")
    sta_if.connect(ssid, password)

    print(f"等待最多 {WIFI_CONNECT_TIMEOUT} 秒钟连接...")
    wait_time = 0
    while not sta_if.isconnected() and wait_time < WIFI_CONNECT_TIMEOUT:
        time.sleep(1)
        wait_time += 1
        print(".", end="")

    if sta_if.isconnected():
        print("\n已成功连接到 WiFi！")
        set_time()
        ifconfig_tuple = sta_if.ifconfig()
        device_ip_on_home_network = ifconfig_tuple[0]
        print("网络配置:", ifconfig_tuple)
        return True, device_ip_on_home_network
    else:
        print(f"\n在 {WIFI_CONNECT_TIMEOUT} 秒内未能连接到 WiFi '{ssid}'。")
        return False, ""

def handle_client(client_socket, ap_ip):
    try:
        request_line_bytes = b""
        while b"\r\n" not in request_line_bytes:
            try:
                chunk = client_socket.recv(1)
                if not chunk:
                    return
                request_line_bytes += chunk
            except OSError as e:
                return

        request_line = request_line_bytes.decode('utf-8').strip()
        print(f"请求行: {request_line}")

        parts = request_line.split()
        if len(parts) < 2:
            print("无效的请求行")
            return

        method, path_and_query = parts[0], parts[1]
        path_parts = path_and_query.split('?', 1)
        path = path_parts[0]
        query_string = path_parts[1] if len(path_parts) > 1 else ""

        headers = {}
        while True:
            header_line_bytes = b""
            while b"\r\n" not in header_line_bytes:
                try:
                    chunk = client_socket.recv(1)
                    if not chunk:
                        return
                    header_line_bytes += chunk
                except OSError as e:
                    return

            header_line = header_line_bytes.decode('utf-8').strip()
            if header_line == "":
                break
            if ':' in header_line:
                key, value = header_line.split(':', 1)
                headers[key.strip().lower()] = value.strip()

        if method == "GET" and path == "/":
            get_params = parse_form_data(query_string)
            ssid_from_get = get_params.get("ssid", "").strip()
            password_from_get = get_params.get("password", "")

            if ssid_from_get:
                print(f"在 GET 参数中发现 SSID: '{ssid_from_get}'。正在尝试连接...")
                is_connected, ip_or_error = attempt_wifi_connection(ssid_from_get, password_from_get)
                if is_connected:
                    html_page = generate_success_html(ip_or_error)
                    response_headers = "HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nConnection: close\r\n\r\n"
                    client_socket.send(response_headers.encode('utf-8'))
                    client_socket.send(html_page.encode('utf-8'))
                    client_socket.close()
                    return
                else:
                    error_message = f"连接到 '{ssid_from_get}' 失败。请检查密码和信号强度，然后重试。"
                    html_page = generate_error_html(error_message, pre_selected_ssid=ssid_from_get)
                    response_headers = "HTTP/1.1 500 Internal Server Error\r\nContent-Type: text/html\r\nConnection: close\r\n\r\n"
                    client_socket.send(response_headers.encode('utf-8'))
                    client_socket.send(html_page.encode('utf-8'))
                    client_socket.close()
                    return
            else:
                html_page = generate_initial_html()
                response_headers = "HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nConnection: close\r\n\r\n"
                client_socket.send(response_headers.encode('utf-8'))
                client_socket.send(html_page.encode('utf-8'))
                client_socket.close()

        elif method == "GET" and path == "/scan":
            ssid_list = scan_wifi_networks()
            response_data = {"networks": ssid_list}
            response_json = json.dumps(response_data)
            response_headers = "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\n\r\n"
            client_socket.send(response_headers.encode('utf-8'))
            client_socket.send(response_json.encode('utf-8'))
            client_socket.close()

        elif method == "POST" and path == "/configure":
            content_length_str = headers.get("content-length")
            if not content_length_str:
                print("缺少 Content-Length 头部")
                client_socket.send("HTTP/1.1 411 Length Required\r\n\r\n".encode())
                client_socket.close()
                return

            try:
                content_length = int(content_length_str)
            except ValueError:
                print("Content-Length 无效")
                client_socket.send("HTTP/1.1 400 Bad Request\r\n\r\n".encode())
                client_socket.close()
                return

            post_data_bytes = recv_all(client_socket, content_length)
            if post_data_bytes is None:
                print("接收 POST 数据时连接关闭")
                return

            post_data_str = post_data_bytes.decode('utf-8')
            print(f"收到的 POST 数据: {post_data_str}")

            form_data = parse_form_data(post_data_str)
            ssid_input = form_data.get("ssid", "").strip()
            password_input = form_data.get("password", "")

            if not ssid_input:
                error_message = "未选择网络。请从列表中选择一个网络。"
                html_page = generate_error_html(error_message, pre_selected_ssid=ssid_input)
                response_headers = "HTTP/1.1 400 Bad Request\r\nContent-Type: text/html\r\nConnection: close\r\n\r\n"
                client_socket.send(response_headers.encode('utf-8'))
                client_socket.send(html_page.encode('utf-8'))
                client_socket.close()
            else:
                is_connected, ip_or_error = attempt_wifi_connection(ssid_input, password_input)
                if is_connected:
                    html_page = generate_success_html(ip_or_error)
                    response_headers = "HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nConnection: close\r\n\r\n"
                    client_socket.send(response_headers.encode('utf-8'))
                    client_socket.send(html_page.encode('utf-8'))
                    client_socket.close()
                else:
                    error_message = f"连接到 '{ssid_input}' 失败。请检查密码和信号强度，然后重试。"
                    html_page = generate_error_html(error_message, pre_selected_ssid=ssid_input)
                    response_headers = "HTTP/1.1 500 Internal Server Error\r\nContent-Type: text/html\r\nConnection: close\r\n\r\n"
                    client_socket.send(response_headers.encode('utf-8'))
                    client_socket.send(html_page.encode('utf-8'))
                    client_socket.close()

        else:
            response_headers = "HTTP/1.1 404 Not Found\r\n\r\n"
            client_socket.send(response_headers.encode('utf-8'))
            client_socket.close()

    except Exception as e:
        print(f"处理客户端时出错: {e}")
        try:
            client_socket.send("HTTP/1.1 500 Internal Server Error\r\n\r\n".encode())
        except:
            pass
    finally:
        try:
            client_socket.close()
        except:
            pass

def main():
    print("--- ESP32-S3 WiFi 设置门户 ---")
    print("正在进行初始 WiFi 接口清理...")
    sta_if = network.WLAN(network.STA_IF)
    ap_if = network.WLAN(network.AP_IF)

    if sta_if.active():
        sta_if.disconnect()
        sta_if.active(False)
    if ap_if.active():
        ap_if.active(False)
    time.sleep(1)
    print("初始清理完成。")

    ap, ap_ip = start_ap(AP_SSID, AP_PASSWORD)
    if not ap:
        print("致命错误：无法启动初始 SoftAP。程序退出。")
        return

    print(f"Web 服务器已在 http://{ap_ip}:{WEB_PORT} 启动")
    print(f"请连接到 WiFi '{AP_SSID}' (密码 '{AP_PASSWORD}')，然后在浏览器中打开 http://{ap_ip}:{WEB_PORT} 。")

    addr = socket.getaddrinfo(ap_ip, WEB_PORT)[0][-1]
    server_socket = socket.socket()
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        server_socket.bind(addr)
    except OSError as e:
        print(f"绑定服务器套接字失败: {e}")
        return
    server_socket.listen(1)
    print(f"Web 服务器已在 http://{ap_ip}:{WEB_PORT} 启动")

    try:
        while True:
            try:
                client_socket, client_addr = server_socket.accept()
                print(f"\n客户端已连接，来自 {client_addr}")
            except OSError as e:
                print(f"接受连接时出错: {e}")
                continue
            handle_client(client_socket, ap_ip)

    except KeyboardInterrupt:
        print("\n服务器被用户停止。")
    except Exception as e:
        print(f"\n主循环中发生未预期的错误: {e}")
    finally:
        server_socket.close()
        print("Web 服务器套接字已关闭。")

if __name__ == "__main__":
    main()