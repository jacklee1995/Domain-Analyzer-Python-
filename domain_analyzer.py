# -*- coding: utf-8 -*-
import os
import ssl
import socket
import datetime
import yaml
import json
from OpenSSL import SSL
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from openpyxl import Workbook
from tqdm import tqdm

# 设置基础目录
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")

def load_config():
    config_path = os.path.join(BASE_DIR, "configs.yaml")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
    except UnicodeDecodeError:
        with open(config_path, "r", encoding="gbk") as f:
            config = yaml.safe_load(f)
    
    # 设置默认值
    config.setdefault('ssl_timeout', 5)
    config.setdefault('excel_prefix', 'SSL-')
    config.setdefault('include_errors', True)
    config.setdefault('output_fields', [
        "Domain", "Issuer", "Subject.countryName", "Subject.stateOrProvinceName", 
        "Subject.organizationName", "Subject.commonName", "Version", "Serial Number", 
        "Not Before", "Not After", "Subject Alternative Names", "OCSP", "CA Issuers", 
        "CRL Distribution Points", "Error"
    ])
    config.setdefault('progress_bar', {
        "desc": "Checking SSL certificates",
        "unit": "domain",
        "colour": "green"
    })
    
    return config

def read_domains(file_path):
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]
    except UnicodeDecodeError:
        with open(file_path, "r", encoding="gbk") as f:
            return [line.strip() for line in f if line.strip()]

def get_ssl_info(hostname, timeout):
    context = ssl.create_default_context()
    
    try:
        with socket.create_connection((hostname, 443), timeout=timeout) as sock:
            with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                cert = ssock.getpeercert()
                
                subject = dict(x[0] for x in cert['subject'])
                issued_to = subject.get('commonName')
                issuer = dict(x[0] for x in cert['issuer'])
                issued_by = issuer.get('commonName')
                
                ssl_info = {
                    "Domain": hostname,
                    "Issuer": issued_by,
                    "Subject.countryName": subject.get('countryName'),
                    "Subject.stateOrProvinceName": subject.get('stateOrProvinceName'),
                    "Subject.organizationName": subject.get('organizationName'),
                    "Subject.commonName": issued_to,
                    "Version": cert.get('version'),
                    "Serial Number": cert.get('serialNumber'),
                    "Not Before": cert.get('notBefore'),
                    "Not After": cert.get('notAfter'),
                    "Subject Alternative Names": cert.get('subjectAltName'),
                    "OCSP": cert.get('OCSP', [""])[0],
                    "CA Issuers": cert.get('caIssuers', [""])[0],
                    "CRL Distribution Points": cert.get('crlDistributionPoints', [""])[0]
                }
                
                return ssl_info
    except Exception as e:
        return {
            "Domain": hostname,
            "Error": str(e)
        }

def format_value(value):
    if isinstance(value, list):
        return ", ".join([format_value(v) for v in value])
    elif isinstance(value, tuple):
        return "/".join([format_value(v) for v in value])
    else:
        return str(value)

def main():
    config = load_config()
    domains_file = config['domains_file']
    output_dir = config['output_directory']

    if not os.path.isabs(domains_file):
        domains_file = os.path.join(BASE_DIR, domains_file)

    if output_dir == "default" or not os.path.isdir(output_dir) or not os.access(output_dir, os.W_OK):
        output_dir = OUTPUT_DIR

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    domains = read_domains(domains_file)

    wb = Workbook()
    ws = wb.active
    ws.append(config['output_fields'])

    progress_bar = tqdm(total=len(domains), **config['progress_bar'])
    
    # 预先打印空行,为信息显示预留空间
    print("\n" * (len(config['output_fields']) + 1))

    for domain in domains:
        progress_bar.set_description(f"Checking: {domain}")
        ssl_info = get_ssl_info(domain, config['ssl_timeout'])
        
        # 将证书信息写入Excel
        row_data = []
        for field in config['output_fields']:
            value = ssl_info.get(field, "")
            if field in ["Not Before", "Not After"] and value:
                value = datetime.datetime.strptime(value, "%b %d %H:%M:%S %Y %Z").strftime("%Y-%m-%d %H:%M:%S")
            else:
                value = format_value(value)
            row_data.append(value)
        ws.append(row_data)
        
        # 准备当前域名的解析信息
        info_lines = []
        for field in config['output_fields']:
            value = ssl_info.get(field, "")
            if field in ["Not Before", "Not After"] and value:
                value = datetime.datetime.strptime(value, "%b %d %H:%M:%S %Y %Z").strftime("%Y-%m-%d %H:%M:%S")
            else:
                value = format_value(value)
            info_lines.append(f"{field}: {str(value)[:50]}")
        
        # 清除之前的信息并打印新信息
        print(f"\033[{len(config['output_fields']) + 1}A")  # 移动光标到预留空间的开始
        print("\033[J", end="")  # 清除从光标位置到屏幕底部的内容
        tqdm.write("\n".join(info_lines))
        
        progress_bar.update(1)

    progress_bar.close()
    output_file = os.path.join(output_dir, f"{config['excel_prefix']}{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}.xlsx")
    wb.save(output_file)
    print(f"\nResults saved to {output_file}")

if __name__ == "__main__":
    main()