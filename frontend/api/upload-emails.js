// Vercel serverless proxy for public POST /api/upload-emails
const RENDER_BACKEND = process.env.RENDER_BACKEND_URL || 'https://unwanted-g96n.onrender.com';

export default async function handler(req, res) {
  try {
    const contentType = req.headers['content-type'] || '';
    let body;

    if (contentType.includes('multipart/form-data')) {
      const formData = await req.formData();
      body = formData;
    } else {
      const rawBody = await req.text();
      body = rawBody;
    }

    const response = await fetch(`${RENDER_BACKEND}/api/upload-emails`, {
      method: 'POST',
      headers: contentType.includes('multipart/form-data') ? {} : { 'Content-Type': 'application/json' },
      body,
    });

    const responseBody = await response.text();
    res.status(response.status);
    const ct = response.headers.get('content-type');
    if (ct) res.setHeader('Content-Type', ct);
    res.send(responseBody);
  } catch (error) {
    console.error('Proxy error:', error.message);
    return res.status(502).json({ detail: 'Backend unavailable' });
  }
}
