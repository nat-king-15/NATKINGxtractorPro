import requests
import re
from urllib.parse import urlparse
import threading 
import json
import cloudscraper
from pyrogram import filters
from Extractor import app
import os
import asyncio
import aiohttp
import base64
from Crypto.Cipher import AES
from Extractor.modules.mix import v2_new
from Crypto.Util.Padding import unpad
from base64 import b64decode
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor
import time 
from config import CHANNEL_ID

log_channel = CHANNEL_ID
log_channel2 = CHANNEL_ID

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
                        return {}
                except json.JSONDecodeError:
                    print(f"Could not parse JSON from the end in {url}")
                    return {}
            else:
                print(f"Could not find JSON at the end for {url}")
                return {}
    except Exception as e:
        print(f"An error occurred during fetch_appx_html_to_json: {e}")
        return {}

async def fetch(session, url, headers):
    try:
        j = await fetch_appx_html_to_json(session, url, headers)
        return j or {}
    except Exception as e:
        print(f"An error occurred while fetching {url}: {str(e)}")
        return {}


def transform_to_vercel_url(extracted_url, api_base, course_id, subject_id, topic_id, token):
    match = re.search(r'/(\d+)-\d+/', extracted_url)
    file_id = match.group(1) if match else extracted_url.split('/')[-1]
    
    api_domain = urlparse(api_base).netloc
    
    # Extension heuristics
    ext = "pdf" if ".pdf" in extracted_url.lower() else "m3u8"
    
    # Format: https://appxsignurl.vercel.app/appx/{api_domain}/{course_id}/{course}.{subject}.{topic}.{file}.{ext}?usertoken={token}&appxv=3
    # Note: v3 skips concept id
    vercel_url = f"https://appxsignurl.vercel.app/appx/{api_domain}/{course_id}/{course_id}.{subject_id}.{topic_id}.{file_id}.{ext}?usertoken={token}&appxv=3"
    
    if ext == "pdf":
        vercel_url += "&pdf=1"
        
    return vercel_url

async def handle_course(session, api_base, bi, si, sn, topic, hdr1, course_name="", app_name="Home"):
    ti = topic.get("topicid")
    tn = topic.get("topic_name")
    
    url = f"{api_base}/get/livecourseclassbycoursesubtopconceptapiv3?courseid={bi}&subjectid={si}&topicid={ti}&conceptid=&start=-1"
    r3 = await fetch(session, url, hdr1)
    video_data = sorted(r3.get("data", []), key=lambda x: x.get("id"))  

    
    tasks = [process_video(session, api_base, bi, si, sn, ti, tn, video, hdr1, course_name, app_name) for video in video_data]
    results = await asyncio.gather(*tasks)
    
    return [line for lines in results if lines for line in lines]

async def process_video(session, api_base, bi, si, sn, ti, tn, video, hdr1, course_name="", app_name="Home"):
    vi = video.get("id")
    vn = video.get("Title")
    lines = []
    
    # Construct breadcrumb string if course_name is provided
    breadcrumb = f"[{app_name} >> {course_name} >> {sn} >> {tn}] " if course_name else ""
    
    try:
        r4 = await fetch(session, f"{api_base}/get/fetchVideoDetailsById?course_id={bi}&video_id={vi}&ytflag=0&folder_wise_course=0", hdr1)
        
        if not r4 or not r4.get("data"):
            print(f"Skipping video ID {vi}: No data found.")
            return None

        vt = r4.get("data", {}).get("Title", "")
        vl = r4.get("data", {}).get("download_link", "")
        fl = r4.get("data", {}).get("video_id", "")
        
        token = hdr1.get("Authorization", "")
        
        if fl:
            dfl = decrypt(fl)
            final_link = f"https://youtu.be/{dfl}"
            lines.append(f"{breadcrumb}{vt} : {final_link}\n")

        if vl:
            dvl = decrypt(vl)
            if ".pdf" not in dvl: 
                v_url = transform_to_vercel_url(dvl, api_base, bi, si, ti, token)
                lines.append(f"{breadcrumb}{vt} : {v_url}\n")
                 
        else:
            encrypted_links = r4.get("data", {}).get("encrypted_links", [])
            if encrypted_links:
                first_link = encrypted_links[0]
                a = first_link.get("path")
                k = first_link.get("key")
                if a and k:
                    da = decrypt(a)
                    k1 = decrypt(k)
                    k2 = decode_base64(k1)
                    v_url = transform_to_vercel_url(da, api_base, bi, si, ti, token)
                    # For Vercel links, user doesn't need to append the key, but I'll leave the key format string strictly as requested by Vercel params if needed. The test links didn't have the key at the end, but they are fully signed. 
                    lines.append(f"{breadcrumb}{vt} : {v_url}*{k2}\n")
                elif a:
                    da = decrypt(a)
                    v_url = transform_to_vercel_url(da, api_base, bi, si, ti, token)
                    lines.append(f"{breadcrumb}{vt} : {v_url}\n")
        
        if "material_type" in r4.get("data", {}):
            mt = r4["data"]["material_type"]
            if mt == "PDF":
                p1 = r4["data"].get("pdf_link", "")
                pk1 = r4["data"].get("pdf_encryption_key", "")
                p2 = r4["data"].get("pdf_link2", "")
                pk2 = r4["data"].get("pdf2_encryption_key", "")
                
                if p1 and pk1:
                    dp1 = decrypt(p1)
                    depk1 = decrypt(pk1)
                    v_url = transform_to_vercel_url(dp1, api_base, bi, si, ti, token)
                    if depk1 == "abcdefg":
                        lines.append(f"{breadcrumb}{vt} : {v_url}\n")
                    else:
                        lines.append(f"{breadcrumb}{vt} : {v_url}*{depk1}\n")
                if p2 and pk2:
                    dp2 = decrypt(p2)
                    depk2 = decrypt(pk2)
                    v_url = transform_to_vercel_url(dp2, api_base, bi, si, ti, token)
                    if depk2 == "abcdefg":
                        lines.append(f"{breadcrumb}{vt} : {v_url}\n")
                    else:
                        lines.append(f"{breadcrumb}{vt} : {v_url}*{depk2}\n")

        
        if "material_type" in r4.get("data", {}):
            mt = r4["data"]["material_type"]
            if mt == "VIDEO":
                p1 = r4["data"].get("pdf_link", "")
                pk1 = r4["data"].get("pdf_encryption_key", "")
                p2 = r4["data"].get("pdf_link2", "")
                pk2 = r4["data"].get("pdf2_encryption_key", "")
                
                if p1 and pk1:
                    dp1 = decrypt(p1)
                    depk1 = decrypt(pk1)
                    v_url = transform_to_vercel_url(dp1, api_base, bi, si, ti, token)
                    if depk1 == "abcdefg":
                        lines.append(f"{breadcrumb}{vt} : {v_url}\n")
                    else:
                        lines.append(f"{breadcrumb}{vt} : {v_url}*{depk1}\n")
                if p2 and pk2:
                    dp2 = decrypt(p2)
                    depk2 = decrypt(pk2)
                    v_url = transform_to_vercel_url(dp2, api_base, bi, si, ti, token)
                    if depk2 == "abcdefg":
                        lines.append(f"{breadcrumb}{vt} : {v_url}\n")
                    else:
                        lines.append(f"{breadcrumb}{vt} : {v_url}*{depk2}\n")
                        
        return lines
    
    except Exception as e:
        print(f"An error occurred while processing video ID {vi}: {str(e)}")
        return None

            
            
THREADPOOL = ThreadPoolExecutor(max_workers=1000)
@app.on_message(filters.command(["appxm"]))

async def appex_v3_txt(app, message, api, name):
    
    api_base = api.replace("http://", "https://") if api.startswith(("http://", "https://")) else f"https://{api}"
    app_name = api_base.replace("http://", "").replace("https://", "").replace("api.classx.co.in","").replace("api.akamai.net.in", "").replace("apinew.teachx.in", "").replace("api.cloudflare.net.in", "").replace("api.appx.co.in", "").replace("/", "").strip()
    
    
    input1 = await app.ask(message.chat.id, (f"SEND MOBILE NUMBER AND PASSWORD IN THIS FORMAT\n\n MOBILE*PASSWORD\n\nᴄᴏᴀᴄʜɪɴɢ ɴᴀᴍᴇ:- {app_name}\n\n OR SEND TOKEN"))
    
    raw_text = input1.text.strip()
    
    
    if '*' in raw_text:
        
        email, password = raw_text.split("*")
        raw_url = f"{api_base}/post/userLogin"
        headers = {
            "Auth-Key": "appxapi",
            "User-Id": "-2",
            "Authorization": "",
            "User_app_category": "",
            "Language": "en",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept-Encoding": "gzip, deflate",
            "User-Agent": "okhttp/4.9.1"
        }
        data = {"email": email, "password": password}
        
        try:
            response = requests.post(raw_url, data=data, headers=headers).json()
            status = response.get("status")

            if status == 200:
    
                userid = response["data"]["userid"]
                token = response["data"]["token"]
            
            elif status == 203:
     
                second_api_url = f"{api_base}/post/userLogin?extra_details=0"
                second_headers = {
                    "auth-key": "appxapi",
                    "client-service": "Appx",
                    "source": "website",
                    "user-agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
                    "accept": "*/*",
                    "accept-language": "en-GB,en-US;q=0.9,en;q=0.8"
                }
                second_data = {
                    "source": "website",
                    "phone": email,
                    "email": email,
                    "password": password,
                    "extra_details": "1"
                }
                
                second_response = requests.post(second_api_url, headers=second_headers, data=second_data).json()
                if second_response.get("status") == 200:
                    userid = second_response["data"]["userid"]
                    token = second_response["data"]["token"]
        except Exception as e:
            print(f"An error occurred: {str(e)}")
            return await message.reply_text("Please try again later. Maybe Password Wrong")
                               

        hdr1 = {
            "Client-Service": "Appx",
            "source": "website",
            "Auth-Key": "appxapi",
            "Authorization": token,
            "User-ID": "1234"
        }
        
    else:
        
        userid = "extracted_userid_from_token"
        token = raw_text
        hdr1 = {
            "Client-Service": "Appx",
            "source": "website",
            "Auth-Key": "appxapi",
            "Authorization": token,
            "User-ID": userid
            }  
        
        
        
    scraper = cloudscraper.create_scraper() 
    try:
        mc1 = scraper.get(f"{api_base}/get/mycoursev2?userid={userid}", headers=hdr1)
        # Using the same regex strategy from fetch_appx_html_to_json if straight json loads fails
        try:
            mc1_json = mc1.json()
        except json.JSONDecodeError:
            text = mc1.text
            match = re.search(r'\{"status":', text, re.DOTALL)
            if match:
                json_str = text[match.start():]
                open_brace_count = 0
                close_brace_count = 0
                json_end = -1
                for i, char in enumerate(json_str):
                    if char == '{': open_brace_count += 1
                    elif char == '}': close_brace_count += 1
                    if open_brace_count > 0 and open_brace_count == close_brace_count:
                        json_end = i + 1; break
                if json_end != -1:
                    mc1_json = json.loads(json_str[:json_end])
                else:
                    raise Exception("Could not find matching brace")
            else:
                raise Exception("JSON payload not found in HTML response")

    except json.JSONDecodeError as e:
        print(f"JSON decode error: {str(e)}")
        return await message.reply_text("Error decoding response from server. Please try again later.")
    except Exception as e:
        print(f"An error occurred: {str(e)}")
        return await message.reply_text(f"An error occurred while fetching your courses. Please try again later. {e}")
    
    FFF = "𝗕𝗔𝗧𝗖𝗛 𝗜𝗗 ➤ 𝗕𝗔𝗧𝗖𝗛 𝗡𝗔𝗠𝗘\n\n"
    valid_ids = []

    if "data" in mc1_json and mc1_json["data"]:
        for ct in mc1_json["data"]:
            ci = ct.get("id")
            cn = ct.get("course_name")
            cp = ct.get("course_thumbnail")
            start = ct.get("start_date")
            end = ct.get("end_date")
            pricing = ct.get("price")
            FFF += f"**`{ci}`   -   `{cn}`**\n\n"
            valid_ids.append(ci)
    else:
        try:
            async with aiohttp.ClientSession() as session:
                j1 = await fetch_appx_html_to_json(session, f"{api_base}/get/mycoursev2?userid={userid}", hdr1)
                
                if not j1:
                    return await message.reply_text("Failed to securely fetch course lists. Try again.")

                FFF = "COURSE-ID  -  COURSE NAME\n\n"
                
                valid_ids = []
                if"data" in j1 and j1["data"]:
                    for ct in j1["data"]:
                    	i = ct.get("id")
                    	cn = ct.get("course_name")
                    	start = ct.get("start_date")
                    	end = ct.get("end_date")
                    	pricing = ct.get("price")
                    	thumbnail = ct.get("course_thumbnail")
                    	
                    	FFF += f"**{i}   -   {cn}**\n\n"
                    	valid_ids.append(i)
                else:
                	
                	await message.reply_text("No course found in ID")
                return
        except json.JSONDecodeError as e:
            print(f"JSON decode error: {str(e)}")
            return await message.reply_text("Error decoding response from server. Please try again later.")
        except Exception as e:
            print(f"An error occurred: {str(e)}")
            return await message.reply_text("NO BATCH PURCHASED")    

    dl = (f"𝗔𝗽𝗽𝘅 𝗟𝗼𝗴𝗶𝗻 𝗦𝘂𝗰𝗲𝘀𝘀✅for {app_name} \n {api_base}\n\n `{raw_text}` \n\n`{token}`\n{FFF}")
    if len(FFF) <= 4096:
        await app.send_message(log_channel, dl)
        await app.send_message(log_channel2, f"`{token}`")
        editable1 = await message.reply_text(f"𝗔𝗽𝗽𝘅 𝗟𝗼𝗴𝗶𝗻 𝗦𝘂𝗰𝗲𝘀𝘀✅\n\n`{token}`\n{FFF}")      
    else:
        plain_FFF = FFF.replace("**", "").replace("`", "")
        file_path = f"{app_name}.txt"
        with open(file_path, "w") as file:
            file.write(f"𝗔𝗽𝗽𝘅 𝗟𝗼𝗴𝗶𝗻 𝗦𝘂𝗰𝗲𝘀𝘀✅for {app_name}\n\nToken: {token}\n\n{plain_FFF}")

        await app.send_document(
            message.chat.id,
            document=file_path,
            caption="Too many batches, so select batch IDs from the text file."
        )
        await app.send_document(log_channel, document=file_path, caption="Too many batches.")
    
        editable1 = None

# Ask for multiple batch IDs separated by '&'
    input2 = await app.ask(message.chat.id, "**Send multiple Course IDs separated by '&' to Download or copy below text to download all batches**\n\n`" + "&".join(valid_ids) + "`")

# Split the input into individual batch IDs
    batch_ids = input2.text.strip().split("&")

# Trim whitespace and filter invalid batch IDs
    batch_ids = [batch.strip() for batch in batch_ids if batch.strip() in valid_ids]

    if not batch_ids:
        await message.reply_text("**Invalid Course ID(s). Please send valid Course IDs from the list.**")
        await input2.delete(True)
        if editable1:
            await editable1.delete(True)
        return

    m1 = await message.reply_text("Processing your requested batches...")

# Process each batch ID one by one
    for raw_text2 in batch_ids:
        m2 = await message.reply_text(f"Extracting batch `{raw_text2}`...")
        start_time =time.time()
        try:
            r = scraper.get(f"{api_base}/get/course_by_id?id={raw_text2}", headers=hdr1).json()
        except json.JSONDecodeError as e:
            print(f"JSON decode error: {str(e)}")
            await message.reply_text("Error decoding response from server. Please try again later.")
            continue
        except Exception as e:
            print(f"An error occurred: {str(e)}")
            await message.reply_text("An error occurred while fetching the course details. Please try again later.")
            continue

        if not r.get("data"):
            course_name = next((ct.get("course_name") for ct in mc1["data"] if ct.get("id") == raw_text2), "Course")
            sanitized_course_name = course_name.replace(':', '_').replace('/', '_')
        
            await v2_new(app, message, token, userid, hdr1, app_name, raw_text2, api_base, sanitized_course_name, start_time, start, end, pricing, input2, m1, m2)
            continue

        for i in r.get("data", []):
            txtn = i.get("course_name")
            filename = f"{raw_text2}_{txtn.replace(':', '_').replace('/', '_')}.txt"

            if '/' in filename:
                filename1 = filename.replace("/", "").replace(" ", "_")
            else:
                filename1 = filename
            
            async with aiohttp.ClientSession() as session:
                with open(filename1, 'w') as f:
                    try:
                        r1 = await fetch(session, f"{api_base}/get/allsubjectfrmlivecourseclass?courseid={raw_text2}&start=-1", hdr1)
            
                        for subject in r1.get("data", []):
                            si = subject.get("subjectid")
                            sn = subject.get("subject_name")

                            r2 = await fetch(session, f"{api_base}/get/alltopicfrmlivecourseclass?courseid={raw_text2}&subjectid={si}&start=-1", hdr1)
                            topics = sorted(r2.get("data", []), key=lambda x: x.get("topicid"))

                            tasks = [handle_course(session, api_base, raw_text2, si, sn, t, hdr1, txtn, app_name) for t in topics]
                            all_data = await asyncio.gather(*tasks)
                
                            for data in all_data:
                                if data:
                                    f.writelines(data)
        
                    except Exception as e:
                        print(f"An error occurred while processing the course: {str(e)}")
                        await message.reply_text("An error occurred while processing the course. Please try again later.")
                        continue
                    
                end_time = time.time()
                elapsed_time = end_time - start_time
                print(f"Elapsed time: {elapsed_time:.1f} seconds")
                np = filename1
            
                c_text = (
                    f"**APP NAME: <b>{app_name}</b>**\n"
                    f"**BatchName:** {raw_text2}_{txtn}\n"
                    f"**Validity Start:**{start}\n"
                    f"**Validity Ends:**{end}\n"
                    f"Elapsed time: {elapsed_time:.1f} seconds\n"
                    f"**Batch Price:** {pricing}\n"
                    f"**course_thumbnail:** <a href={cp}>Thumbnail</a>"
                )
            
                try:
                    await input2.delete(True)
                    await m1.delete(True)
                    await m2.delete(True)
                    await app.send_document(message.chat.id, filename1, caption=c_text)
                    await app.send_document(log_channel, filename1, caption=c_text)
                    
            
                except Exception as e:
                    print(f"An error occurred while sending the document: {str(e)}")
                
                    course_name = next((ct.get("course_name") for ct in mc1["data"] if ct.get("id") == raw_text2), "Course")
                    sanitized_course_name = course_name.replace(':', '_').replace('/', '_')
                    await v2_new(app, message, token, userid, hdr1, app_name, raw_text2, api_base, sanitized_course_name, start_time, start, end, pricing, input2, m1, m2)
                finally:
                    if os.path.exists(filename1):
                        os.remove(filename1)



