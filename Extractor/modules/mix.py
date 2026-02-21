import asyncio
import aiohttp
import json
import re
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
from base64 import b64decode
from pyrogram import filters
import cloudscraper
from Extractor import app
from config import CHANNEL_ID
import os
import base64
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

log_channel = CHANNEL_ID
def decrypt(enc):
    enc = b64decode(enc.split(':')[0])
    key = '638udh3829162018'.encode('utf-8')
    iv = 'fedcba9876543210'.encode('utf-8')
    if len(enc) == 0:
        return ""
    cipher = AES.new(key, AES.MODE_CBC, iv)
    plaintext = unpad(cipher.decrypt(enc), AES.block_size)
    return plaintext.decode('utf-8')

def decode_base64(encoded_str):
    try:
        decoded_bytes = base64.b64decode(encoded_str)
        decoded_str = decoded_bytes.decode('utf-8')
        return decoded_str
    except Exception as e:
        return f"Error decoding string: {e}"

async def fetch_appx_html_to_json(session, url, headers=None, data=None):
    try:
        if data:
            async with session.post(url, headers=headers, data=data) as response:
                text = await response.text()
        else:
            async with session.get(url, headers=headers) as response:
                text = await response.text()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r'\{"status":', text, re.DOTALL)
            if match:
                json_str = text[match.start():]
                try:
                    open_brace_count = 0
                    close_brace_count = 0
                    json_end = -1
                    for i, char in enumerate(json_str):
                        if char == '{':
                            open_brace_count += 1
                        elif char == '}':
                            close_brace_count += 1
                        if open_brace_count > 0 and open_brace_count == close_brace_count:
                            json_end = i + 1
                            break
                    if json_end != -1:
                        return json.loads(json_str[:json_end])
                    else:
                        print(f"Could not find matching closing brace }} in {url}")
                        return None
                except json.JSONDecodeError:
                    print(f"Could not parse JSON from the end in {url}")
                    return None
            else:
                print(f"Could not find JSON at the end for {url}")
                return None
    except Exception as e:
        print(f"An error occurred during fetch_appx_html_to_json: {e}")
        return None

def transform_to_vercel_url_v2(extracted_url, api_base, course_id, folder_id, token):
    match = re.search(r'/(\d+)-\d+/', extracted_url)
    file_id = match.group(1) if match else extracted_url.split('/')[-1]
    
    api_domain = urlparse(api_base).netloc
    ext = "pdf" if ".pdf" in extracted_url.lower() else "m3u8"
    
    # Format for v2 (folder-based): course_id.folder_id.item
    vercel_url = f"https://appxsignurl.vercel.app/appx/{api_domain}/{course_id}/{course_id}.{folder_id}.{file_id}.{ext}?usertoken={token}&appxv=3"
    
    if ext == "pdf":
        vercel_url += "&pdf=1"
        
    return vercel_url

async def fetch_item_details(session, api_base, course_id, folder_id, item, headers, token):
    fi = item.get("id")
    vt = item.get("Title", "")
    outputs = []  

    try:
        r4 = await fetch_appx_html_to_json(session, f"{api_base}/get/fetchVideoDetailsById?course_id={course_id}&folder_wise_course=1&ytflag=0&video_id={fi}", headers)
        if r4:
            data = r4.get("data")
            if not data:
                return []

            vt = data.get("Title", "")
            vl = data.get("download_link", "")

            if vl:
                dvl = decrypt(vl)
                if ".pdf" not in dvl:
                    v_url = transform_to_vercel_url_v2(dvl, api_base, course_id, folder_id, token)
                    outputs.append(f"{vt}:{v_url}")
            else:
                encrypted_links = data.get("encrypted_links", [])
                for link in encrypted_links:
                    a = link.get("path")
                    k = link.get("key")

                    if a and k:
                        k1 = decrypt(k)
                        k2 = decode_base64(k1)
                        da = decrypt(a)
                        v_url = transform_to_vercel_url_v2(da, api_base, course_id, folder_id, token)
                        outputs.append(f"{vt}:{v_url}*{k2}")
                        break
                    elif a:
                        da = decrypt(a)
                        v_url = transform_to_vercel_url_v2(da, api_base, course_id, folder_id, token)
                        outputs.append(f"{vt}:{v_url}")
                        break

            if "material_type" in data:
                mt = data["material_type"]
                if mt == "VIDEO":
                    p1 = data.get("pdf_link", "")
                    pk1 = data.get("pdf_encryption_key", "")
                    p2 = data.get("pdf_link2", "")
                    pk2 = data.get("pdf2_encryption_key", "")
                    if p1 and pk1:
                        dp1 = decrypt(p1)
                        depk1 = decrypt(pk1)
                        v_url = transform_to_vercel_url_v2(dp1, api_base, course_id, folder_id, token)
                        if depk1 == "abcdefg":
                            outputs.append(f"{vt}:{v_url}")
                        else:
                            outputs.append(f"{vt}:{v_url}*{depk1}")
                    
                        
                            
                    if p2 and pk2:
                        dp2 = decrypt(p2)
                        depk2 = decrypt(pk2)
                        v_url = transform_to_vercel_url_v2(dp2, api_base, course_id, folder_id, token)
                        if depk2 == "abcdefg":
                            outputs.append(f"{vt}:{v_url}")
                        else:
                            outputs.append(f"{vt}:{v_url}*{depk2}")
        else:
            print(f"Error: Unexpected response for video ID {fi}")
            return []
    except Exception as e:
        print(f"An error occurred while fetching details for video ID {fi}: {str(e)}")
        return []

    return outputs
    
                    
        
async def fetch_folder_contents(session, api_base, course_id, folder_id, headers, token):
    outputs = []  

    try:
        j = await fetch_appx_html_to_json(session, f"{api_base}/get/folder_contentsv2?course_id={course_id}&parent_id={folder_id}", headers)
        if j:
            tasks = []
            if "data" in j:
                for item in j["data"]:
                    mt = item.get("material_type")
                    tasks.append(fetch_item_details(session, api_base, course_id, folder_id, item, headers, token))
                    if mt == "FOLDER":
                        tasks.append(fetch_folder_contents(session, api_base, course_id, item["id"], headers, token))

            if tasks:
                results = await asyncio.gather(*tasks)
                for res in results:
                    if res:  
                        outputs.extend(res)
    except Exception as e:
        print(f"Error fetching folder contents for folder {folder_id}: {str(e)}")
        outputs.append(f"Error fetching folder contents for folder {folder_id}. Error: {e}")

    return outputs

async def v2_new(app, message, token, userid, hdr1, app_name, raw_text2, api_base, sanitized_course_name, start_time, start, end, pricing, input2, m1, m2):
    async with aiohttp.ClientSession() as session:
        
        j2 = await fetch_appx_html_to_json(session, f"{api_base}/get/folder_contentsv2?course_id={raw_text2}&parent_id=-1", hdr1)
        if not j2 or not j2.get("data"):
            return await message.reply_text("No data found in the response. Try switching to v3 and retry.")
        
        
        filename = f"{sanitized_course_name}.txt"

        all_outputs = []        
        tasks = []
        if "data" in j2:
            for item in j2["data"]:        
                tasks.append(fetch_item_details(session, api_base, raw_text2, -1, item, hdr1, token))
                if item["material_type"] == "FOLDER":
                    tasks.append(fetch_folder_contents(session, api_base, raw_text2, item["id"], hdr1, token))
        if tasks:
            results = await asyncio.gather(*tasks)
            for res in results:
                if res:  
                    all_outputs.extend(res)  

        with open(filename, 'w') as f:
            for output_line in all_outputs:
                f.write(output_line + '\n')

        end_time = time.time()
        elapsed_time = end_time - start_time
        c_text = (f"**AppName:** {app_name}\n"
                  f"**BatchName:** {sanitized_course_name}\n"
                  f"**Batch Start Date:** {start}\n"
                  f"**Validity Ends On:** {end}\n"
                  f"Elapsed time: {elapsed_time:.1f} seconds\n"
                  f"**Batch Purchase At:** {pricing}")

        await input2.delete(True)
        await m1.delete(True)
        await m2.delete(True)
        await app.send_document(message.chat.id, filename, caption=c_text)
        await app.send_document(log_channel, filename, caption = c_text)
        os.remove(filename)
        await message.reply_text("Done✅")
                              
