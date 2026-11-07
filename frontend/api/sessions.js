// Vercel serverless proxy for public GET /api/sessions
const RENDER_BACKEND = process.env.RENDER_BACKEND_URL || 'https://unwanted-g96n.onrender.com';

export default async function handler(req, res) {
  try {
    const response = await fetch(`${RENDER_BACKEND}/api/sessions`, {
      method: 'GET',
      headers: { 'Content-Type': 'application/json' },
    });
    const responseBody = await response.text();
    res.status(response.status);
    const contentType = response.headers.get('content-type');
    if (contentType) res.setHeader('Content-Type', contentType);
    res.send(responseBody);
  } catch (error) {
    console.error('Proxy error:', error.message);
    return res.status(502).json({ detail: 'Backend unavailable' });
  }
}
