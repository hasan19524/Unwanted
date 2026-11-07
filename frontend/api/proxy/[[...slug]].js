// Vercel serverless proxy for protected Render backend endpoints
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

  // Extract path from URL
  let path = '';
  try {
    const urlObj = new URL(url, `http://${req.headers.host}`);
    path = urlObj.pathname;
  } catch {
    return res.status(400).json({ detail: 'Invalid request URL' });
  }

  // Strip /proxy prefix to get the actual API path for Render
  const apiPath = path.replace('/proxy', '');

  // Only allow POST to /api/session/start and DELETE to /api/session/{id}
  if (method === 'POST' && apiPath === '/api/session/start') {
    return await proxyRequest(req, res, `${RENDER_BACKEND}${apiPath}`, adminKey);
  }

  if (method === 'DELETE' && apiPath.startsWith('/api/session/')) {
    return await proxyRequest(req, res, `${RENDER_BACKEND}${apiPath}`, adminKey);
  }

  return res.status(404).json({ detail: 'Not found' });
}

async function proxyRequest(req, res, targetUrl, adminKey) {
  try {
    const body = req.body || {};
    const headers = {
      'Content-Type': 'application/json',
      'X-Admin-Key': adminKey,
    };

    const response = await fetch(targetUrl, {
      method: req.method,
      headers,
      body: req.method === 'GET' ? undefined : JSON.stringify(body),
    });

    const responseBody = await response.text();

    // Forward status code
    res.status(response.status);

    // Forward relevant response headers
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
