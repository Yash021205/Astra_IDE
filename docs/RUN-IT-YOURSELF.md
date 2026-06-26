# Run ASTRA-IDE Yourself (no Claude needed)

VM: **astra-cluster-a** · Zone: **asia-south1-a** · Static IP: **34.14.181.224**
Live site: **https://34-14-181-224.sslip.io**

---

## Step 1 — Start the VM

### Option A: GUI (easiest)
1. Go to https://console.cloud.google.com/compute/instances
2. Find **astra-cluster-a** in the list.
3. Tick its checkbox → click **START / RESUME** at the top.
4. Wait ~1-2 minutes (status dot turns green).

### Option B: One command (PowerShell)
```powershell
gcloud compute instances start astra-cluster-a --zone asia-south1-a
```

> The external IP stays **34.14.181.224** every time (it's reserved).

---

## Step 2 — Open an SSH terminal window

### Option A: GUI (opens a browser terminal)
On the VM instances page, click the **SSH** button on the **astra-cluster-a** row.
A black terminal window opens in your browser. (This uses Google's IAP, so it works even though our network blocks port 22.)

### Option B: SSH from your own PowerShell terminal
```powershell
gcloud compute ssh astra-cluster-a --zone asia-south1-a --tunnel-through-iap
```
This drops you into the VM's shell (prompt becomes `mishr@astra-cluster-a:~$`).

> Plain `gcloud compute ssh astra-cluster-a --zone asia-south1-a` (without `--tunnel-through-iap`) will hang — our network blocks direct port 22. **Always include `--tunnel-through-iap`.**

---

## Step 3 — Run the project (inside the SSH terminal)

**Usually you DON'T need to do anything** — the containers auto-start when the VM boots (restart policy). Just wait ~2 min after Step 1 and open the site.

If the site doesn't load, run this in the SSH terminal:
```bash
cd ~/astra-ide/deploy
PUBLIC_HOST=34.14.181.224 docker compose -f docker-compose.yml -f docker-compose.https.yml up -d
```

Check everything is running:
```bash
docker ps
```
You should see 6-7 containers (frontend, backend, collab, postgres, redis, minio, caddy) all `Up`.

---

## Step 4 — Open the site

Browser → **https://34-14-181-224.sslip.io**

(First load after a fresh start can take ~30s while containers finish booting.)

---

## When you're done — STOP the VM to save credits

### GUI
VM instances page → tick **astra-cluster-a** → **STOP**.

### Command
```powershell
gcloud compute instances stop astra-cluster-a --zone asia-south1-a
```

> Stopping keeps the disk and the IP. Next time, just repeat Step 1. You only pay for disk storage while stopped (a few cents/day), not compute.

---

## Quick troubleshooting

| Problem | Fix |
|---|---|
| Site won't load right after start | Wait 1-2 more min, then refresh. Containers boot after the VM. |
| Still won't load | SSH in (Step 2) → run the `docker compose ... up -d` from Step 3. |
| `gcloud` not recognized | Open a fresh PowerShell, or use the GUI options. |
| SSH hangs forever | You forgot `--tunnel-through-iap`. Add it, or use the GUI SSH button. |
| Google login fails on site | Use email/password login instead (register a new account). |
