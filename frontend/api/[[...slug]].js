// Vercel serverless proxy for all backend routes
// Reads ADMIN_KEY from server-side environment only - never exposed to browser

const RENDER_BACKEND = process.env.RENDER_BACKEND_URL || 'https://unwanted-g96n.onrender.com';

export default async function handler(req, res) {
  // Validate server-side secret exists
  const adminKey = process.env.ADMIN_KEY;
  if (!adminKey) {
    return res.status(500).json({ detail: 'Server configuration error' });
  }

  const { method } = req;
  const { url } = req;

  let path = '';
  try {
    const urlObj = new URL(url, `http://${req.headers.host}`);
    path = urlObj.pathname;
  } catch {
    return res.status(400).json({ detail: 'Invalid request URL' });
  }

  // Strip /api prefix to get backend path
  const apiPath = path.startsWith('/api/') ? path : '/api' + path;

  // Forward ALL API requests to Render
  try {
    let body = {};
    if (method !== 'GET' && method !== 'HEAD') {
      const rawBody = await req.text();
      if (rawBody) {
        try {
          body = JSON.parse(rawBody);
        } catch {
          body = {};
        }
      }
    }

    const headers = {
      'Content-Type': 'application/json',
    };

    // Inject admin key for mutating requests
    if (method === 'POST' || method === 'DELETE' || method === 'PUT') {
      headers['X-Admin-Key'] = adminKey;
    }

    const response = await fetch(`${RENDER_BACKEND}${apiPath}`, {
      method,
      headers,
      body: method === 'GET' || method === 'HEAD' ? undefined : JSON.stringify(body),
    });

    const responseBody = await response.text();
    res.status(response.status);

    const contentType = response.headers.get('content-type');
    if (contentType) {
      res.setHeader('Content-Type', contentType);
    }

    res.send(responseBody);
  } catch (error) {
    console.error('Proxy error:', error.message);
    return res.status(502).json({ detail: 'Backend unavailable' });
  }
}
