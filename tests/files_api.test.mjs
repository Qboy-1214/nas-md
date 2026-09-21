import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

function loadApi() {
  const context = vm.createContext({
    console,
    window: {
      location: { origin: 'http://localhost', pathname: '/admin' },
    },
  });
  vm.runInContext(readFileSync(new URL('../web/files.js', import.meta.url), 'utf8'), context);
  return context;
}

test('putFile rejects a stable non-2xx write error', async () => {
  const context = loadApi();
  vm.runInContext(
    `API.request = async () => ({
      ok: false,
      status: 500,
      json: async () => ({
        errorCode: 'write_failed',
        message: 'Unable to save file',
      }),
    })`,
    context,
  );
  const putFile = vm.runInContext('API.putFile.bind(API)', context);

  await assert.rejects(putFile('mount-0', '/failed.md', 'content'), (error) => {
    assert.equal(error.code, 'write_failed');
    assert.equal(error.status, 500);
    assert.equal(error.message, 'Unable to save file');
    return true;
  });
});

test('putFile rejects a successful response whose JSON cannot be parsed', async () => {
  const context = loadApi();
  vm.runInContext(
    `API.request = async () => ({
      ok: true,
      status: 200,
      json: async () => { throw new SyntaxError('Unexpected end of JSON input'); },
    })`,
    context,
  );
  const putFile = vm.runInContext('API.putFile.bind(API)', context);

  await assert.rejects(putFile('mount-0', '/invalid.md', 'content'), (error) => {
    assert.equal(error.code, 'invalid_response');
    assert.equal(error.status, 200);
    assert.equal(error.message, 'Invalid response from server');
    return true;
  });
});

test('putFile rejects a successful response with an empty JSON body', async () => {
  const context = loadApi();
  vm.runInContext(
    `API.request = async () => ({
      ok: true,
      status: 200,
      json: async () => null,
    })`,
    context,
  );
  const putFile = vm.runInContext('API.putFile.bind(API)', context);

  await assert.rejects(putFile('mount-0', '/empty.md', 'content'), (error) => {
    assert.equal(error.code, 'invalid_response');
    assert.equal(error.status, 200);
    assert.equal(error.message, 'Invalid response from server');
    return true;
  });
});
