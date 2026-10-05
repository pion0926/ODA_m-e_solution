import { Client } from '../../redesign/kordoc/node_modules/@modelcontextprotocol/sdk/dist/esm/client/index.js';
import { StdioClientTransport } from '../../redesign/kordoc/node_modules/@modelcontextprotocol/sdk/dist/esm/client/stdio.js';
import { StreamableHTTPClientTransport } from '../../redesign/kordoc/node_modules/@modelcontextprotocol/sdk/dist/esm/client/streamableHttp.js';
import path from 'node:path';
const root = path.resolve(import.meta.dirname, '../..');
for (const [name, args, env] of [
  ['kordoc', [path.join(root, 'redesign/kordoc/node_modules/kordoc/dist/mcp.js')], { KORDOC_OFFLINE: '1', KORDOC_ROOT: root }],
  ['playwright', [path.join(root, 'node_modules/@playwright/mcp/cli.js'), '--headless', '--isolated', '--block-service-workers'], {}],
]) {
  const client = new Client({ name: 'kodame-tooling-check', version: '1.0.0' });
  try {
    await client.connect(new StdioClientTransport({ command: process.execPath, args, env: { ...process.env, ...env }, stderr: 'pipe' }));
    const { tools } = await client.listTools();
    if (!tools.length) throw Error(`${name}: no tools`);
    if (name === 'kordoc') {
      const result = await client.callTool({ name: 'parse_metadata', arguments: { file_path: path.join(root, 'samples/5-1. 종료평가 결과보고서 placeholder.hwpx') } });
      if (result.isError) throw Error('kordoc metadata check failed');
    }
    if (name === 'playwright') {
      const result = await client.callTool({ name: 'browser_navigate', arguments: { url: 'about:blank' } });
      if (result.isError) throw Error('Playwright MCP could not launch its isolated browser: ' + JSON.stringify(result.content));
      await client.callTool({ name: 'browser_close', arguments: {} });
    }
    console.log(JSON.stringify({ server: name, tools: tools.length, initialized: true }));
  } finally { await client.close(); }
}
if (process.argv.includes('--docs')) {
  const client = new Client({ name: 'kodame-docs-check', version: '1.0.0' });
  try {
    await client.connect(new StreamableHTTPClientTransport(new URL('https://developers.openai.com/mcp')));
    const { tools } = await client.listTools();
    if (!tools.length) throw Error('Official documentation MCP returned no tools');
    console.log(JSON.stringify({ server: 'openaiDeveloperDocs', tools: tools.length, initialized: true }));
  } finally { await client.close(); }
}
