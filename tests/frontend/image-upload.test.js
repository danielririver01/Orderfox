const fs = require('fs');
const path = require('path');
const assert = require('assert');

const src = fs.readFileSync(
  path.join(__dirname, '..', '..', 'app', 'static', 'js', 'image-upload.js'),
  'utf8'
);

class MockFileReader {
  readAsDataURL() {
    this.result = 'data:image/jpeg;base64,FAKEDATA';
    setTimeout(() => this.onload && this.onload({ target: this }), 0);
  }
}

class MockImage {
  set src(value) {
    this._src = value;
    this.width = 4000;
    this.height = 3000;
    setTimeout(() => this.onload && this.onload(), 0);
  }
  get src() { return this._src; }
}

const fakeBlob = new Blob([new Uint8Array(16)], { type: 'image/jpeg' });

const mockDocument = {
  createElement(tag) {
    if (tag === 'canvas') {
      return {
        width: 0,
        height: 0,
        getContext() {
          return { drawImage() {} };
        },
        toBlob(cb) { cb(fakeBlob); },
      };
    }
    return {};
  },
};

class MockDataTransfer {
  constructor() {
    this._list = [];
    this.items = { add: (item) => this._list.push(item) };
  }
  get files() { return this._list; }
}

global.FileReader = MockFileReader;
global.Image = MockImage;
global.document = mockDocument;
global.DataTransfer = MockDataTransfer;

eval(src);

function makeFile(name, type, sizeBytes) {
  return new File([new Uint8Array(sizeBytes)], name, { type });
}

async function tick() {
  await new Promise((r) => setTimeout(r, 10));
}

async function waitUntil(cond, timeoutMs = 3000) {
  const start = Date.now();
  while (!cond()) {
    if (Date.now() - start > timeoutMs) return false;
    await new Promise((r) => setTimeout(r, 5));
  }
  return true;
}

(async () => {
  // 1. Imagen estándar pequeña pasa tal cual (sin re-codificar)
  const small = makeFile('icon.png', 'image/png', 1024);
  const r1 = await compressImageFile(small);
  assert.strictEqual(r1, small, 'PNG pequeño debe pasar sin comprimir');

  // 2. Foto grande (caso Android) se comprime a JPEG
  const big = makeFile('IMG_2026.JPG', 'image/jpeg', 3 * 1024 * 1024);
  const r2 = await compressImageFile(big);
  assert.notStrictEqual(r2, big, 'Foto grande debe re-codificarse');
  assert.strictEqual(r2.type, 'image/jpeg', 'Salida debe ser JPEG');
  assert.ok(r2.name.endsWith('.jpg'), 'Nombre debe terminar en .jpg');

  // 3. HEIC se re-codifica a JPEG
  const heic = makeFile('IMG_0001.heic', 'image/heic', 2 * 1024 * 1024);
  const r3 = await compressImageFile(heic);
  assert.strictEqual(r3.type, 'image/jpeg', 'HEIC debe convertirse a JPEG');
  assert.ok(r3.name.endsWith('.jpg'), 'HEIC debe nombrarse .jpg');

  // 4. No-imagen pasa tal cual
  const txt = makeFile('nota.txt', 'text/plain', 2048);
  const r4 = await compressImageFile(txt);
  assert.strictEqual(r4, txt, 'No-imagen no debe tocarse');

  // 5. prepareImageUpload: reemplaza input.files con la foto comprimida y hace preview
  const origCompress = compressImageFile;
  compressImageFile = function (...args) {
    const p = origCompress.apply(this, args);
    p.then(
      (f) => console.log('compress resolved:', f === args[0] ? 'ORIGINAL' : 'NEW', f && f.name),
      (e) => console.log('compress rejected:', e)
    );
    return p;
  };
  const direct = await compressImageFile(big);
  console.log('direct tras wrap:', direct === big ? 'ORIGINAL' : 'NEW', direct && direct.name);
  const inputBig = { files: [big], value: 'C:\\fakepath\\IMG_2026.JPG' };
  let previewCalled = false;
  prepareImageUpload(inputBig, () => { previewCalled = true; });
  const done = await waitUntil(() => previewCalled);
  console.log('DEBUG inputBig.files[0].name:', inputBig.files[0] && inputBig.files[0].name);
  assert.ok(done, 'Debe llamarse el callback de preview');
  assert.ok(inputBig.files.length === 1 && inputBig.files[0] !== big,
    'input.files debe contener la versión comprimida');

  // 6. prepareImageUpload: imagen pequeña conserva el archivo original y hace preview
  const inputSmall = { files: [small], value: 'C:\\fakepath\\icon.png' };
  let previewCalled2 = false;
  prepareImageUpload(inputSmall, () => { previewCalled2 = true; });
  const done2 = await waitUntil(() => previewCalled2);
  assert.ok(done2, 'Preview debe llamarse también para imágenes pequeñas');
  assert.strictEqual(inputSmall.files[0], small,
    'Imagen pequeña debe conservarse sin cambios');

  console.log('✔ image-upload.js: 6/6 asserts OK');
})().catch((err) => {
  console.error('✘ Fallo en test JS:', err.message);
  process.exit(1);
});
