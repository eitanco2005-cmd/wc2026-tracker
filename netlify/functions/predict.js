// Netlify Function: predict.js
// Uses Node.js built-in https module — works on all Netlify runtimes

const https = require("https");

exports.handler = async function(event) {
  const headers = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Content-Type": "application/json"
  };

  if (event.httpMethod === "OPTIONS") {
    return { statusCode: 200, headers, body: "" };
  }

  if (event.httpMethod !== "POST") {
    return { statusCode: 405, headers, body: JSON.stringify({ error: "Method not allowed" }) };
  }

  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey) {
    return {
      statusCode: 500, headers,
      body: JSON.stringify({ error: "ANTHROPIC_API_KEY not set in Netlify environment variables." })
    };
  }

  let body;
  try { body = JSON.parse(event.body); }
  catch(e) { return { statusCode: 400, headers, body: JSON.stringify({ error: "Invalid JSON" }) }; }

  const postData = JSON.stringify({
    model: "claude-sonnet-4-6",
    max_tokens: 600,
    messages: body.messages
  });

  return new Promise((resolve) => {
    const options = {
      hostname: "api.anthropic.com",
      path: "/v1/messages",
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Content-Length": Buffer.byteLength(postData),
        "x-api-key": apiKey,
        "anthropic-version": "2023-06-01"
      }
    };

    const req = https.request(options, (res) => {
      let data = "";
      res.on("data", chunk => data += chunk);
      res.on("end", () => {
        try {
          const parsed = JSON.parse(data);
          resolve({ statusCode: 200, headers, body: JSON.stringify(parsed) });
        } catch(e) {
          resolve({ statusCode: 500, headers, body: JSON.stringify({ error: "Failed to parse Claude response", raw: data }) });
        }
      });
    });

    req.on("error", (e) => {
      resolve({ statusCode: 500, headers, body: JSON.stringify({ error: e.message }) });
    });

    req.write(postData);
    req.end();
  });
};
