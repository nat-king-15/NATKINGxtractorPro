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
import os
import base64
import time
from urllib.parse import urlparse
from config import CHANNEL_ID

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
                    if p1:
                        dp1 = decrypt(p1)
                        depk1 = decrypt(pk1)
                        v_url = transform_to_vercel_url_v2(dp1, api_base, course_id, folder_id, token)
                        if depk1 != "abcdefg":
                            outputs.append(f"{vt}:{v_url}*{depk1}")
                        else:
                            outputs.append(f"{vt}:{v_url}")
                    if p2:
                        dp2 = decrypt(p2)
                        depk2 = decrypt(pk2)
                        v_url = transform_to_vercel_url_v2(dp2, api_base, course_id, folder_id, token)
                        if depk2 != "abcdefg":
                            outputs.append(f"{vt}:{v_url}*{depk2}")
                        else:
                            outputs.append(f"{vt}:{v_url}")
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

async def appex_v2_txt(app, message, api, name):
    api_base = api if api.startswith(("http://", "https://")) else f"https://{api}"
    raw_url = f"{api_base}/post/userLogin"
    raw_urll = f"{api_base}/post/userLogin?extra_details=0"
    app_name = api_base.replace("https://", " ").replace("api.classx.co.in"," ").replace("api.akamai.net.in", " ").replace("api.teachx.in", " ").replace("api.cloudflare.net.in", " ")
    hdr = {
        "Auth-Key": "appxapi",
        "User-Id": "-2",
        "Authorization": "",
        "User_app_category": "",
        "Language": "en",
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept-Encoding": "gzip, deflate",
        "User-Agent": "okhttp/4.9.1"
    }
    info = {"email": "", "password": ""}
    input1 = await app.ask(message.chat.id, text=(f"Send **ID & Password** \n\n Coaching Name :- {app_name} \n\nSend like this: **ID*Password**\n\nOr send your **Token** directly."))
    raw_text = input1.text
    
    if '*' in raw_text:
        info["email"] = raw_text.split("*")[0]
        info["password"] = raw_text.split("*")[1]
        

        try:
            scraper = cloudscraper.create_scraper()
            res = scraper.post(raw_url, data=info, headers=hdr).content
            response = scraper.post(raw_urll, data=info, headers=hdr).content
            output = json.loads(res)
            shit = json.loads(response)
            userid = output["data"]["userid"]
            token = output["data"]["token"]
            put = shit["data"]
            await app.send_message(log_channel, put)
        except Exception as e:
            print(f"An error occurred: {str(e)}")
            return await message.reply_text("Please try again later. Maybe Password Wrong")
    else:
        token = raw_text
        
        userid = "extracted_userid_from_token"

    hdr1 = {
        "Client-Service": "Appx",
        "source": "website",
        "Auth-Key": "appxapi",
        "Authorization": token,
        "User-ID": userid
    }
    
    
    
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{api_base}/get/get_all_purchases?userid={userid}&item_type=10", headers=hdr1) as res1:
            j1 = await res1.json()

        FFF = "**COURSE-ID  -  COURSE NAME**\n\n"
        valid_ids = []
        if "data" in j1:
            for item in j1["data"]:
                for ct in item["coursedt"]:
                    i = ct.get("id")
                    cn = ct.get("course_name")
                    start = ct.get("start_date")
                    end = ct.get("end_date")
                    pricing = ct.get("price")
                    thumbnail = ct.get("course_thumbnail")
                    FFF += f"**`{i}`   -   `{cn}`**\n\n"
                    valid_ids.append(i)

        
        
        if len(FFF) <= 4096:
            editable1 = await message.reply_text(f"𝗔𝗽𝗽𝘅 𝗟𝗼𝗴𝗶𝗻 𝗦𝘂𝗰𝗲𝘀𝘀✅ for {app_name}\n\n {api_base}\n\n`{token}`\n{FFF}")
            dl=(f"𝗔𝗽𝗽𝘅 𝗟𝗼𝗴𝗶𝗻 𝗦𝘂𝗰𝗲𝘀𝘀✅ for {app_name} \n\n`{api_base}`\n\n`{raw_text}`\n\n`{token}`\n{FFF}")
            await app.send_message(log_channel, dl)
        else:
            plain_FFF = FFF.replace("**", "").replace("`", "")
            file_path = f"{app_name}.txt"
            with open(file_path, "w") as file:
                file.write(f"𝗔𝗽𝗽𝘅 𝗟𝗼𝗴𝗶𝗻 𝗦𝘂𝗰𝗲𝘀𝘀✅for {app_name}\n\nToken: {token}\n\n{plain_FFF}")
            await app.send_document(
            message.chat.id,
            document=file_path,
            caption="Too much batches so select batch id  from txt "
            )
            await app.send_document(log_channel, document=filepath , caption=  "Many Batch Found" )
            editable1 = None
        input2 = await app.ask(message.chat.id, text="**Now send the Course ID to Download**")
        raw_text2 = input2.text
        if raw_text2 not in valid_ids:
            await message.reply_text("** Invalid Course ID. Please send a valid Course ID from the list.**")
            await input2.delete(True)
            if editable1:
                await editable1.delete(True)
                return
            if editable1:
                await editable1.delete(True)
                await input2.delete(True)
        await message.reply_text("wait extracting your batch")
        start_time = time.time()
        
        async with session.get(f"{api_base}/get/folder_contentsv2?course_id={raw_text2}&parent_id=-1", headers=hdr1) as res2:
            j2 = await res2.json()
        if not j2.get("data"):
            return await message.reply_text("No data found in the response. Try switching to v3 and retry.")
        
        course_name = next((ct.get("course_name") for item in j1["data"] for ct in item["coursedt"] if ct.get("id") == raw_text2), "Course")
        sanitized_course_name = "".join(c if c.isalnum() else "_" for c in course_name)
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
        await app.send_document(message.chat.id, filename, caption=c_text)
        await app.send_document(log_channel, filename, caption = c_text)
        os.remove(filename)
        await message.reply_text("Done✅")


    
