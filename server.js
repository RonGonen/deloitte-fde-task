const http = require("node:http");
const fs = require("node:fs");
const path = require("node:path");
const { answerQuestion } = require("./src/agent");

const PUBLIC_DIR = path.join(__dirname, "public");
const PORT = Number(process.env.PORT) || 3000;
const CONTENT_TYPES = {
  ".css": "text/css; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
};

function sendJson(response, statusCode, body) {
  response.writeHead(statusCode, { "Content-Type": "application/json; charset=utf-8" });
  response.end(JSON.stringify(body));
}

function readJsonBody(request, limit = 12_000) {
  return new Promise((resolve, reject) => {
    let body = "";
    request.setEncoding("utf8");
    request.on("data", (chunk) => {
      body += chunk;
      if (body.length > limit) {
        reject(Object.assign(new Error("Request body is too large."), { statusCode: 413 }));
        request.destroy();
      }
    });
    request.on("end", () => {
      try {
        resolve(JSON.parse(body));
      } catch {
        reject(Object.assign(new Error("Request body must be valid JSON."), { statusCode: 400 }));
      }
    });
    request.on("error", reject);
  });
}

function serveStatic(request, response, urlPath) {
  const requestedPath = urlPath === "/" ? "/index.html" : decodeURIComponent(urlPath);
  const filePath = path.resolve(PUBLIC_DIR, `.${requestedPath}`);
  if (!filePath.startsWith(`${PUBLIC_DIR}${path.sep}`)) {
    response.writeHead(403).end("Forbidden");
    return;
  }

  fs.readFile(filePath, (error, content) => {
    if (error) {
      response.writeHead(404).end("Not found");
      return;
    }
    response.writeHead(200, { "Content-Type": CONTENT_TYPES[path.extname(filePath)] || "application/octet-stream" });
    response.end(content);
  });
}

const server = http.createServer(async (request, response) => {
  const url = new URL(request.url, `http://${request.headers.host || "localhost"}`);
  if (request.method === "GET" && url.pathname === "/api/status") {
    sendJson(response, 200, {
      status: "ready",
      llmEnabled: Boolean(process.env.OPENAI_API_KEY),
      liveSources: ["FAA annual airport enplanements", "OurAirports coordinate reference"],
      demoSections: ["airport congestion", "route frequency", "SFO pressure inputs"],
    });
    return;
  }

  if (request.method === "POST" && url.pathname === "/api/ask") {
    try {
      const body = await readJsonBody(request);
      if (typeof body.question !== "string" || !body.question.trim()) {
        sendJson(response, 400, { error: "Enter an airport question to continue." });
        return;
      }
      const answer = await answerQuestion(body.question.trim(), body.previousIntent || null);
      sendJson(response, 200, answer);
    } catch (error) {
      sendJson(response, error.statusCode || 500, { error: error.message || "The request could not be processed." });
    }
    return;
  }

  if (request.method === "GET" || request.method === "HEAD") {
    serveStatic(request, response, url.pathname);
    return;
  }
  response.writeHead(405, { Allow: "GET, HEAD, POST" }).end("Method not allowed");
});

server.listen(PORT, "127.0.0.1", () => {
  console.log(`Airport Intelligence Desk running at http://127.0.0.1:${PORT}`);
});
