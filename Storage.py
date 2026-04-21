import hashlib
import requests
import os
import json
VERCEL_BLOB_TOKEN = os.environ.get('BLOB_READ_WRITE_TOKEN')


class Storage:
    @classmethod
    def get_filename(cls, barrel_name):
        safe_id = hashlib.md5(barrel_name.strip().encode()).hexdigest()
        return f"barrel_{safe_id}.json"

    @classmethod
    def get_data(cls, barrel_name, create_if_missing=False):
        filename = cls.get_filename(barrel_name)
        
        if VERCEL_BLOB_TOKEN:
            headers = {"Authorization": f"Bearer {VERCEL_BLOB_TOKEN}"}
            try:
                list_url = f"https://blob.vercel-storage.com/?prefix={filename}"
                list_resp = requests.get(list_url, headers=headers).json()
                
                if list_resp.get("blobs"):
                    blob_url = list_resp["blobs"][0]["url"]
                    data = requests.get(blob_url).json()
                    data['barrel_name'] = barrel_name
                    return data
            except Exception as e:
                print(f"Blob Read Error: {e}")

        if not create_if_missing:
            return None

        # ECHTE LEGE DATA (Geen dummies meer)
        return {
            "barrel_name": barrel_name,
            "water_level": 0.0,
            "max_liters": 200.0, 
            "battery": 0,
            "last_updated": 0,
            "today_version": 1,
            "tomorrow_version": 1,
            "today_schedule": "-" * 48, # 48 lege slots
            "tomorrow_schedule": "-" * 48, # 48 lege slots
            "cancel_rainy": False
        }

    @classmethod
    def save_data(cls, barrel_name, data):
        filename = cls.get_filename(barrel_name)
        data['barrel_name'] = barrel_name
        
        if VERCEL_BLOB_TOKEN:
            headers = {
                "Authorization": f"Bearer {VERCEL_BLOB_TOKEN}",
                "x-add-random-suffix": "false",
                "Content-Type": "application/json"
            }
            requests.put(
                f"https://blob.vercel-storage.com/{filename}",
                headers=headers,
                data=json.dumps(data)
            )