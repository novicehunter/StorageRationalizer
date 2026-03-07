#!/usr/bin/env python3
"""
Google Photos Access Test
Tests multiple approaches to access Google Photos without restricted scopes.
Run: python3 gphotos_test.py
"""

import json, requests
from pathlib import Path
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

CREDS_FILE = Path.home() / "Desktop/StorageRationalizer/credentials/google_credentials.json"
TOKEN_FILE  = Path.home() / "Desktop/StorageRationalizer/credentials/google_token.json"

print("=" * 60)
print("Google Photos Access Test")
print("=" * 60)

# ── Load existing token ────────────────────────────────────────
creds = None
if TOKEN_FILE.exists():
    creds = Credentials.from_authorized_user_file(str(TOKEN_FILE))
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    print(f"✓ Token loaded. Scopes: {creds.scopes}")
else:
    print("✗ No token file found")
    exit(1)

headers = {'Authorization': f'Bearer {creds.token}'}

# ── Test 1: Drive API — hidden Google Photos folder ────────────
print("\n── Test 1: Google Photos folder in Drive ──")
try:
    service = build('drive', 'v3', credentials=creds)
    resp = service.files().list(
        q="name='Google Photos' and mimeType='application/vnd.google-apps.folder' and trashed=false",
        fields="files(id,name,parents)",
        includeItemsFromAllDrives=True,
        supportsAllDrives=True,
        corpora='allDrives'
    ).execute()
    folders = resp.get('files', [])
    if folders:
        print(f"  ✓ Found {len(folders)} Google Photos folder(s) in Drive")
        for f in folders:
            print(f"    ID: {f['id']} Name: {f['name']}")
        # Try to list files inside it
        folder_id = folders[0]['id']
        children = service.files().list(
            q=f"'{folder_id}' in parents and trashed=false",
            fields="files(id,name,mimeType,size)",
            pageSize=5
        ).execute()
        print(f"  ✓ Sample files inside: {len(children.get('files',[]))}")
        for f in children.get('files', []):
            print(f"    {f.get('name')} — {f.get('mimeType')} — {f.get('size','?')} bytes")
    else:
        print("  ✗ No Google Photos folder found in Drive")
except Exception as e:
    print(f"  ✗ Error: {e}")

# ── Test 2: Drive API — all images including hidden ────────────
print("\n── Test 2: All images via Drive API (spaces=photos) ──")
try:
    resp = service.files().list(
        q="mimeType contains 'image/' and trashed=false",
        fields="files(id,name,mimeType,size,createdTime)",
        pageSize=5,
        spaces='photos',
    ).execute()
    files = resp.get('files', [])
    if files:
        print(f"  ✓ Found images in photos space: {len(files)} (sample)")
        for f in files:
            print(f"    {f.get('name')} — {f.get('createdTime','?')}")
    else:
        print("  ✗ No images found in photos space")
except Exception as e:
    print(f"  ✗ Error: {e}")

# ── Test 3: Drive API — all drives including photos ────────────
print("\n── Test 3: All images across all drives ──")
try:
    resp = service.files().list(
        q="(mimeType contains 'image/' or mimeType contains 'video/') and trashed=false",
        fields="files(id,name,mimeType,size,createdTime)",
        pageSize=10,
        includeItemsFromAllDrives=True,
        supportsAllDrives=True,
        corpora='allDrives'
    ).execute()
    files = resp.get('files', [])
    print(f"  {'✓' if files else '✗'} Found {len(files)} images/videos (sample of 10)")
    for f in files[:5]:
        print(f"    {f.get('name')} — {f.get('mimeType')}")
except Exception as e:
    print(f"  ✗ Error: {e}")

# ── Test 4: Photos Library API with current token ──────────────
print("\n── Test 4: Photos Library API (current token) ──")
try:
    resp = requests.get(
        'https://photoslibrary.googleapis.com/v1/mediaItems',
        headers=headers, params={'pageSize': 5}, timeout=15
    )
    print(f"  Status: {resp.status_code}")
    if resp.status_code == 200:
        items = resp.json().get('mediaItems', [])
        print(f"  ✓ Got {len(items)} items!")
        for item in items:
            print(f"    {item.get('filename')} — {item.get('mimeType')}")
    else:
        print(f"  ✗ {resp.json().get('error',{}).get('message','Unknown error')}")
except Exception as e:
    print(f"  ✗ Error: {e}")

# ── Test 5: Re-auth with photoslibrary scope only ──────────────
print("\n── Test 5: Fresh auth with ONLY photoslibrary scope ──")
print("  (This will open a browser window)")
try:
    PHOTOS_ONLY_TOKEN = Path.home() / "Desktop/StorageRationalizer/credentials/gphotos_only_token.json"
    PHOTOS_SCOPE = ['https://www.googleapis.com/auth/photoslibrary.readonly']

    pcreds = None
    if PHOTOS_ONLY_TOKEN.exists():
        pcreds = Credentials.from_authorized_user_file(str(PHOTOS_ONLY_TOKEN), PHOTOS_SCOPE)
        if pcreds.expired and pcreds.refresh_token:
            pcreds.refresh(Request())

    if not pcreds or not pcreds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(str(CREDS_FILE), PHOTOS_SCOPE)
        pcreds = flow.run_local_server(port=0)
        with open(PHOTOS_ONLY_TOKEN, 'w') as f:
            f.write(pcreds.to_json())

    resp = requests.get(
        'https://photoslibrary.googleapis.com/v1/mediaItems',
        headers={'Authorization': f'Bearer {pcreds.token}'},
        params={'pageSize': 5}, timeout=15
    )
    print(f"  Status: {resp.status_code}")
    if resp.status_code == 200:
        items = resp.json().get('mediaItems', [])
        print(f"  ✓ SUCCESS — Got {len(items)} items with photos-only scope!")
        for item in items:
            print(f"    {item.get('filename')} — {item.get('mimeType')}")
    else:
        print(f"  ✗ {resp.json().get('error',{}).get('message','Unknown error')}")
except Exception as e:
    print(f"  ✗ Error: {e}")

print("\n" + "=" * 60)
print("Test complete.")
print("=" * 60)
