import hashlib
import requests
import os
import json
import time

VERCEL_BLOB_TOKEN = os.environ.get('BLOB_READ_WRITE_TOKEN')

class Storage:
    @classmethod
    def get_filename(cls, barrel_name):
        safe_id = hashlib.md5(barrel_name.strip().encode()).hexdigest()
        return f"barrel_{safe_id}.json"

    @classmethod
    def get_data(cls, barrel_name, create_if_missing=False):
        filename = cls.get_filename(barrel_name)
        
        # 1. Try Vercel Blob
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
        # 2. Local Fallback (for testing without Vercel)
        else:
            if os.path.exists(filename):
                with open(filename, 'r') as f:
                    data = json.load(f)
                    data['barrel_name'] = barrel_name
                    return data

        if not create_if_missing:
            return None

        # ECHTE LEGE DATA
        return {
            "barrel_name": barrel_name,
            "water_level": 0.0,
            "max_liters": 200.0, 
            "battery": 0,
            "last_updated": 0,
            "today_version": 1,
            "tomorrow_version": 1,
            "today_schedule": "-" * 48, 
            "tomorrow_schedule": "-" * 48, 
            "cancel_rainy": False,
            "history": [] # Fixed: Always initialize empty history
        }

    @classmethod
    def save_data(cls, barrel_name, data):
        filename = cls.get_filename(barrel_name)
        
        # Fixed: No need to re-fetch data from Vercel! Just use the passed data dict.
        history = data.get('history', [])
        
        # Add new point: [timestamp, liters]
        history.append([int(time.time()), data.get('water_level', 0.0)])
        
        # Keep only the last 100 entries
        data['history'] = history
        data['barrel_name'] = barrel_name
        
        if VERCEL_BLOB_TOKEN:
            headers = {
                "Authorization": f"Bearer {VERCEL_BLOB_TOKEN}",
                "x-add-random-suffix": "false",
                "Content-Type": "application/json"
            }
            try:
                requests.put(
                    f"https://blob.vercel-storage.com/{filename}",
                    headers=headers,
                    data=json.dumps(data)
                )
            except Exception as e:
                print(f"Blob Write Error: {e}")
        else:
            # Local fallback save
            with open(filename, 'w') as f:
                json.dump(data, f)