# Class Link Tracker

Find out who shared your Google Meet link with outsiders. Each student gets a unique tracked link that redirects to your Meet. The app logs every visit and shows you a list of students whose links were used by unknown devices.

## How It Works

1. Teacher enters her name, Meet link, email template (with `{{LINK}}` placeholder), and student emails
2. App sends each student a **unique tracked link** via email
3. Student clicks link → app logs the visit (IP, city, device, time, which app opened it) → redirects to Meet
4. Teacher checks the dashboard → sees a **list of all students who shared the link** with outsiders
5. Teacher clicks **Reset** → all data wiped, clean slate for next class

## Setup

### 1. Create a dedicated Gmail account (for sending)

1. Create a new Gmail account (e.g., `mrs.sharma.class@gmail.com`)
2. Enable 2-Factor Authentication on it
3. Go to Google Account → Security → App Passwords → generate a 16-char password
4. Save the email and app password

### 2. Configure the backend

```bash
cd backend
cp .env.example .env
```

Edit `.env`:
```
SMTP_EMAIL=your-sender@gmail.com
SMTP_PASSWORD=your-16-char-app-password
SMTP_DISPLAY_NAME=Mrs. Sharma
APP_BASE_URL=http://localhost:8000
ADMIN_KEY=your-secret-key
```

### 3. Install dependencies

```bash
# Backend
cd backend
pip install -r requirements.txt

# Frontend
cd ../frontend
npm install
```

### 4. Run (development)

```bash
# Terminal 1: Backend
cd backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000

# Terminal 2: Frontend (dev server with hot reload)
cd frontend
npm run dev
```

Open http://localhost:5173 in your browser.

### 5. Build for production

```bash
cd frontend
npm run build
```

The built frontend will be in `frontend/dist/` and served by the backend automatically.

Then run just the backend:
```bash
cd backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

Open http://localhost:8000 in your browser.

## Deployment

### Backend (e.g., Render, Railway, Fly.io)
- Set environment variables from `.env`
- Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`

### Frontend
- Build with `npm run build`
- The backend serves the built files from `frontend/dist/`
- Or deploy separately to Vercel/Netlify and update `CORS_ORIGINS` and `APP_BASE_URL`

## Important Notes

- **Session history**: All sessions are saved in SQLite. Browse past sessions in the sidebar.
- **Delete sessions**: Remove individual sessions and all their data when done.
- **Temporary data**: Delete a session to wipe everything. Nothing stored permanently unless you keep it.
- **One chance**: Test everything yourself first before sending to students.
- **Invisible tracking**: Students never know they're tracked. Emails look like normal class invites.
- **Clean domain**: Use a domain that looks like a class/school site, not "tracker" or "unwanted".
- **Gmail limits**: ~500 emails/day via SMTP. Fine for a class.

## Tech Stack

- **Backend**: Python FastAPI
- **Frontend**: React + Vite
- **Database**: SQLite (lightweight, file-based, persists session history)
- **Email**: Gmail SMTP with app password
- **Geo lookup**: ip-api.com (free, no key needed)
