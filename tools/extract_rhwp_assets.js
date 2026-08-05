const fs = require("fs");

const text = fs.readFileSync("assets/rhwp/assets/index.js", "utf8");
const re = /[`"']([^`"']+\.(?:wasm|js|css|png|ico|webmanifest))[`"']/g;
const assets = new Set();
let match;
while ((match = re.exec(text))) {
  assets.add(match[1]);
}
console.log([...assets].sort().join("\n"));
