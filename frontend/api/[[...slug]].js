// Single Vercel serverless proxy for ALL backend API routes.
//
// Handles every /api/* path and method, forwards JSON and multipart
// bodies untouched, and normalizes paths regardless of whether Vercel
// hands us the full URL or one relative to this function's mount point.

export const maxDuration = 60;

const RENDER_BACKEND = (
  process.env.RENDER_BACKEND_URL || 'https://unwanted-g96n.onrender.com'
).replace(/\/+$/, '');

export default async function handler(req, res) {
  // Figure out the original path. req.url may be the full path
  // (/api/proxy/session/start) or relative to this function's mount
  // point (/proxy/session/start) depending on how Vercel routed it.
  let pathname = '';
  let search = '';
  try {
    const urlObj = new URL(req.url, `http://${req.headers.host || 'localhost'}`);
    pathname = urlObj.pathname;
    search = urlObj.search;
  } catch {
    return res.status(400).json({ detail: 'Invalid request URL' });
  }

  // Normalize to the backend path: strip leading /api and an optional
  // /proxy prefix, so both /api/session/start and /api/proxy/session/start
  // land on the backend's /api/session/start.
  let rest = pathname.replace(/^\/+/, '');
  if (rest.startsWith('api/')) rest = rest.slice(4);
  if (rest.startsWith('proxy/')) rest = rest.slice(6);
  const backendPath = `/api/${rest}${search}`;

  const method = (req.method || 'GET').toUpperCase();

  try {
    // Read the raw body once (works for JSON and multipart alike).
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    const rawBody = chunks.length ? Buffer.concat(chunks) : undefined;

    const headers = {};
    const hasBody = rawBody && method !== 'GET' && method !== 'HEAD';
    if (hasBody) {
      // Preserve the original content type (incl. multipart boundary)
      headers['Content-Type'] =
        req.headers['content-type'] || 'application/json';
    }

    // Pass through client identity headers so the backend logs real data
    for (const h of ['x-forwarded-for', 'x-real-ip', 'user-agent', 'referer']) {
      if (req.headers[h]) headers[h] = req.headers[h];
    }

    const upstream = await fetch(`${RENDER_BACKEND}${backendPath}`, {
      method,
      headers,
      body: hasBody ? rawBody : undefined,
      signal: AbortSignal.timeout(55000),
    });

    res.status(upstream.status);
    const ct = upstream.headers.get('content-type');
    if (ct) res.setHeader('Content-Type', ct);
    const buf = Buffer.from(await upstream.arrayBuffer());
    return res.send(buf);
  } catch (error) {
    const timedOut =
      error && (error.name === 'TimeoutError' || error.code === 'ABORT_ERR');
    console.error('Proxy error:', backendPath, error && error.message);
    return res.status(timedOut ? 504 : 502).json({
      detail: timedOut
        ? 'Backend took too long to respond (it may be waking up from sleep - retry in a minute)'
        : 'Backend unavailable',
    });
  }
}
