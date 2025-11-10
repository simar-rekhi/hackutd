# Auth0 Configuration for Multi-Device Access

## Problem
When accessing the application from another device on your network, Auth0 authentication may fail because the redirect URI is not configured in your Auth0 application settings.

## Solution

### Step 1: Get Your Network IP Address
Run this command to find your current IP:
```bash
ifconfig | grep "inet " | grep -v 127.0.0.1 | awk '{print $2}' | head -1
```

**Current IP:** `172.20.10.6` (static IP - use this for configuration)

### Step 2: Configure Auth0 Allowed URLs

1. Go to [Auth0 Dashboard](https://manage.auth0.com/)
2. Navigate to **Applications** → Your Application (`koEERgWqiyyNe3Ry1QSAbLtKyahWdg2y`)
3. Go to **Settings** tab
4. Scroll to **Allowed Callback URLs**
5. Add the following URLs (replace `YOUR_IP` with your actual IP):
   ```
   http://localhost:5000/dashboard,
   http://127.0.0.1:5000/dashboard,
   http://YOUR_IP:5000/dashboard,
   http://YOUR_IP:5000/login,
   http://localhost:5000/login,
   http://127.0.0.1:5000/login
   ```
   Example (if your IP is 10.176.214.219):
   ```
   http://localhost:5000/dashboard,
   http://127.0.0.1:5000/dashboard,
   http://10.176.214.219:5000/dashboard,
   http://10.176.214.219:5000/login,
   http://localhost:5000/login,
   http://127.0.0.1:5000/login
   ```

6. Scroll to **Allowed Logout URLs**
7. Add the same URLs:
   ```
   http://localhost:5000/login,
   http://127.0.0.1:5000/login,
   http://YOUR_IP:5000/login
   ```

8. Scroll to **Allowed Web Origins**
9. Add:
   ```
   http://localhost:5000,
   http://127.0.0.1:5000,
   http://YOUR_IP:5000
   ```

10. Click **Save Changes**

### Step 3: Test from Second Device

1. On the server laptop, start the Flask app:
   ```bash
   python main.py
   ```

2. On the second laptop, open browser and go to:
   ```
   http://YOUR_IP:5000
   ```

3. You should now be able to authenticate with Auth0

## Note
If your IP address changes (common with DHCP), you'll need to update the Auth0 settings with the new IP address, or consider:
- Setting a static IP on your server laptop
- Using a domain name with dynamic DNS
- Adding a wildcard pattern if Auth0 supports it (check Auth0 documentation)

## Troubleshooting

If authentication still fails:
1. Check browser console for errors
2. Verify both devices are on the same network
3. Check that Auth0 settings were saved correctly
4. Try clearing browser cache and cookies
5. Check that the Flask server is running with `host='0.0.0.0'` (already configured in `main.py`)

