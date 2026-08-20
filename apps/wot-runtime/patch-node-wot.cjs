const fs = require('fs');
const path = require('path');

const file = path.join(__dirname, 'node_modules/@node-wot/binding-http/dist/http-client-impl.js');
let code = fs.readFileSync(file, 'utf8');

// Replace doFetch to read body before checkFetchResponse
const oldDoFetch = [
  'async doFetch(request) {',
  '        const result = await this._fetch(request);',
  '        if (HttpClient.isOAuthTokenExpired(result, this.credential)) {',
  '            this.credential = await this.credential.refreshToken();',
  '            const resultAuth = await this._fetch(await this.credential.sign(request));',
  '            this.checkFetchResponse(resultAuth);',
  '            return resultAuth;',
  '        }',
  '        this.checkFetchResponse(result);',
  '        return result;',
  '    }',
].join('\n');

const newDoFetch = [
  'async doFetch(request) {',
  '        const result = await this._fetch(request);',
  '        if (HttpClient.isOAuthTokenExpired(result, this.credential)) {',
  '            this.credential = await this.credential.refreshToken();',
  '            const resultAuth = await this._fetch(await this.credential.sign(request));',
  '            const __body2 = await resultAuth.clone().text().catch(() => "");',
  '            resultAuth.__bodyText = __body2;',
  '            this.checkFetchResponse(resultAuth);',
  '            return resultAuth;',
  '        }',
  '        const __body = await result.clone().text().catch(() => "");',
  '        result.__bodyText = __body;',
  '        this.checkFetchResponse(result);',
  '        return result;',
  '    }',
].join('\n');

code = code.replace(oldDoFetch, newDoFetch);

// Patch checkFetchResponse to include body text
code = code.replace(
  'throw new Error(`Client error: ${response.statusText}`)',
  'throw new Error(`Client error: ${response.statusText} [${response.status}] ` + (response.__bodyText ? JSON.stringify(response.__bodyText).substring(0,1000) : "(no body)"))'
);
code = code.replace(
  'throw new Error(`Server error: ${response.statusText}`)',
  'throw new Error(`Server error: ${response.statusText} [${response.status}] ` + (response.__bodyText ? JSON.stringify(response.__bodyText).substring(0,1000) : "(no body)"))'
);

fs.writeFileSync(file, code);
console.log('Patched node-wot HTTP client error handling');
