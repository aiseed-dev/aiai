// Receives the contact form and keeps each message as one JSON file in R2.
// Cloudflare Pages runs this at POST /api/contact.
// Bindings (Settings > Bindings in the Pages project):
//   CONTACTS          R2 bucket where the messages are kept (required)
//   TURNSTILE_SECRET  Turnstile secret key; set it to check for bots (optional)

const LIMITS = { name: 100, reply: 200, message: 5000 };

function back(form, request, hash) {
  // Return to the page the form was on; only paths on this site
  const page = String(form.get("page") || "/");
  const path = page.startsWith("/") && !page.startsWith("//") ? page : "/";
  return Response.redirect(new URL(path + "#" + hash, request.url).toString(), 303);
}

async function human(form, request, secret) {
  const res = await fetch("https://challenges.cloudflare.com/turnstile/v0/siteverify", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      secret,
      response: String(form.get("cf-turnstile-response") || ""),
      remoteip: request.headers.get("CF-Connecting-IP") || undefined,
    }),
  });
  const result = await res.json();
  return result.success === true;
}

export async function onRequestPost({ request, env }) {
  let form;
  try {
    form = await request.formData();
  } catch {
    return new Response("Bad request", { status: 400 });
  }
  // A field people do not see; bots fill it in
  if (String(form.get("website") || "")) return back(form, request, "sent");
  const entry = {};
  for (const [k, max] of Object.entries(LIMITS)) {
    entry[k] = String(form.get(k) || "").trim();
    if (entry[k].length > max) return back(form, request, "error");
  }
  if (!entry.reply || !entry.message) return back(form, request, "error");
  if (env.TURNSTILE_SECRET && !(await human(form, request, env.TURNSTILE_SECRET))) {
    return back(form, request, "error");
  }
  const now = new Date();
  entry.received = now.toISOString();
  const key = `contact/${now.toISOString().replace(/[:.]/g, "-")}-${crypto.randomUUID()}.json`;
  await env.CONTACTS.put(key, JSON.stringify(entry, null, 2), {
    httpMetadata: { contentType: "application/json; charset=utf-8" },
  });
  return back(form, request, "sent");
}
