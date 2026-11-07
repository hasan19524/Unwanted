// Vercel serverless proxy for public Render backend endpoints
const RENDER_BACKEND = process.env.RENDER_BACKEND_URL || 'https://unwanted-g96n.onrender.com';

export default async function handler(req, res) {
  const { method } = req;
  const { url } = req;

  let path = '';
  try {
    const urlObj = new URL(url, `http://${req.headers.host}`);
    path = urlObj.pathname;
  } catch {
    return res.status(400).json({ detail: 'Invalid request URL' });
  }

  // Only allow specific public paths
  if (method === 'GET' && (path === '/api/sessions' || path.startsWith('/api/session/'))) {
    return await proxyRequest(req, res, `${RENDER_BACKEND}${path}`);
  }

  if (method === 'POST' && path === '/api/upload-emails') {
    return await proxyRequest(req, res, `${RENDER_BACKEND}/api/upload-emails`);
  }

  return res.status(404).json({ detail: 'Not found' });
}

async function proxyRequest(req, res, targetUrl) {
  try {
    const headers = {
      'Content-Type': 'application/json',
    };

    let body = undefined;
    if (req.method === 'POST') {
      const contentType = req.headers['content-type'] || '';
      if (contentType.includes('multipart/form-data')) {
        // Forward multipart as-is for file uploads
        const formData = await req.formData();
        headers['Content-Type'] = formData.getBoundary() 
          ? `multipart/form-data; boundary=${formData.getBoundary()}` 
          : 'multipart/form-data';
        body = formData;
      } else {
        const rawBody = await req.text();
        body = rawBody;
      }
    }

    const response = await fetch(targetUrl, {
      method: req.method,
      headers,
      body,
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
