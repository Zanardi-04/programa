/* Leitor local de CSV e XLSX. Nenhum dado sai do aparelho. */
'use strict';
(() => {
  const LIMIT = 8 * 1024 * 1024;
  const decoder = new TextDecoder('utf-8');

  function csvRows(text) {
    const source = text.replace(/^\uFEFF/, '').replace(/^sep=([,;\t])\r?\n/i, '');
    const first = source.split(/\r?\n/).find(line => line.trim()) || '';
    function score(delimiter) {
      let count = 0, quoted = false;
      for (let i = 0; i < first.length; i++) {
        if (first[i] === '"') {
          if (quoted && first[i + 1] === '"') i++;
          else quoted = !quoted;
        } else if (!quoted && first[i] === delimiter) count++;
      }
      return count;
    }
    const delimiter = [';', ',', '\t'].sort((a, b) => score(b) - score(a))[0];
    if (!score(delimiter)) throw new Error('Não encontrei colunas na planilha CSV.');
    const rows = []; let row = [], cell = '', quoted = false;
    for (let i = 0; i < source.length; i++) {
      const c = source[i];
      if (c === '"') {
        if (quoted && source[i + 1] === '"') { cell += '"'; i++; }
        else quoted = !quoted;
      } else if (c === delimiter && !quoted) {
        row.push(cell); cell = '';
      } else if ((c === '\r' || c === '\n') && !quoted) {
        if (c === '\r' && source[i + 1] === '\n') i++;
        row.push(cell); cell = '';
        if (row.some(v => String(v).trim())) rows.push(row);
        row = [];
      } else {
        cell += c;
      }
    }
    if (quoted) throw new Error('O CSV contém aspas sem fechamento.');
    row.push(cell);
    if (row.some(v => String(v).trim())) rows.push(row);
    if (rows.length > 5001) throw new Error('Importe no máximo 5.000 linhas por arquivo.');
    return rows;
  }

  function parseXml(text) {
    const doc = new DOMParser().parseFromString(text, 'application/xml');
    if (doc.getElementsByTagName('parsererror').length)
      throw new Error('O arquivo Excel contém XML inválido.');
    return doc;
  }
  const tags = (element, name) => Array.from(element.getElementsByTagNameNS('*', name));
  const firstTag = (element, name) => tags(element, name)[0];
  const normalizePath = input => {
    const parts = [];
    input.replace(/^\/+/, '').split('/').forEach(s => {
      if (s === '..') parts.pop();
      else if (s && s !== '.') parts.push(s);
    });
    return parts.join('/');
  };
  const columnIndex = address => {
    const name = String(address).match(/^[A-Z]+/i)?.[0].toUpperCase() || '';
    let result = 0;
    for (const c of name) result = result * 26 + c.charCodeAt(0) - 64;
    return result - 1;
  };

  function zipIndex(buffer) {
    const dv = new DataView(buffer), bytes = new Uint8Array(buffer);
    let end = -1;
    for (let i = bytes.length - 22; i >= Math.max(0, bytes.length - 65557); i--) {
      if (dv.getUint32(i, true) === 0x06054b50) { end = i; break; }
    }
    if (end < 0) throw new Error('Este arquivo não é um XLSX válido.');
    const count = dv.getUint16(end + 10, true);
    let offset = dv.getUint32(end + 16, true);
    if (count > 1000) throw new Error('A planilha contém arquivos internos demais.');
    const found = new Map();
    for (let i = 0; i < count; i++) {
      if (offset + 46 > bytes.length || dv.getUint32(offset, true) !== 0x02014b50)
        throw new Error('O XLSX possui uma estrutura ZIP inválida.');
      const method = dv.getUint16(offset + 10, true);
      const packed = dv.getUint32(offset + 20, true);
      const unpacked = dv.getUint32(offset + 24, true);
      const nLen = dv.getUint16(offset + 28, true), xLen = dv.getUint16(offset + 30, true);
      const cLen = dv.getUint16(offset + 32, true), local = dv.getUint32(offset + 42, true);
      const name = decoder.decode(bytes.subarray(offset + 46, offset + 46 + nLen));
      if (name.startsWith('xl/')) found.set(name, {method, packed, unpacked, local});
      offset += 46 + nLen + xLen + cLen;
    }
    async function read(path, optional = false) {
      const meta = found.get(path);
      if (!meta) {
        if (optional) return null;
        throw new Error('Não encontrei ' + path + ' no arquivo Excel.');
      }
      if (meta.unpacked > 12 * 1024 * 1024 || meta.packed > LIMIT)
        throw new Error('Uma parte da planilha é grande demais.');
      if (dv.getUint32(meta.local, true) !== 0x04034b50)
        throw new Error('O arquivo Excel está corrompido.');
      const start = meta.local + 30 + dv.getUint16(meta.local + 26, true) + dv.getUint16(meta.local + 28, true);
      if (start + meta.packed > bytes.length) throw new Error('O arquivo Excel está incompleto.');
      const packedBytes = bytes.slice(start, start + meta.packed);
      if (meta.method === 0) return decoder.decode(packedBytes);
      if (meta.method !== 8 || typeof DecompressionStream === 'undefined')
        throw new Error('Não foi possível descompactar esta planilha neste navegador.');
      const stream = new Blob([packedBytes]).stream().pipeThrough(new DecompressionStream('deflate-raw'));
      const raw = await new Response(stream).arrayBuffer();
      if (raw.byteLength > 12 * 1024 * 1024)
        throw new Error('Uma parte da planilha é grande demais.');
      return decoder.decode(raw);
    }
    return {read, names: [...found.keys()]};
  }

  async function xlsxRows(file) {
    const zip = zipIndex(await file.arrayBuffer());
    const workbook = parseXml(await zip.read('xl/workbook.xml'));
    const sheets = tags(workbook, 'sheet');
    if (!sheets.length) throw new Error('O Excel não tem abas.');
    const preferred = sheets.find(s => s.getAttribute('state') !== 'hidden' && /lan[cç]amentos|movimenta[cç][oõ]es|rendimentos/i.test(s.getAttribute('name') || ''))
                   || sheets.find(s => s.getAttribute('state') !== 'hidden') || sheets[0];
    const relationsText = await zip.read('xl/_rels/workbook.xml.rels', true);
    const relations = relationsText ? tags(parseXml(relationsText), 'Relationship') : [];
    const relId = preferred.getAttribute('r:id') || preferred.getAttributeNS('http://schemas.openxmlformats.org/officeDocument/2006/relationships', 'id');
    const rel = relations.find(r => r.getAttribute('Id') === relId);
    let path = rel ? (rel.getAttribute('Target') || '') : 'worksheets/sheet1.xml';
    if (!path.startsWith('/')) path = 'xl/' + path;
    path = normalizePath(path);
    if (!zip.names.includes(path)) {
      path = zip.names.find(n => /^xl\/worksheets\/sheet\d+\.xml$/.test(n));
    }
    if (!path) throw new Error('Não encontrei os lançamentos na planilha.');
    const sheet = parseXml(await zip.read(path));
    const sharedText = await zip.read('xl/sharedStrings.xml', true);
    const shared = sharedText ? tags(parseXml(sharedText), 'si').map(el => tags(el, 't').map(t => t.textContent || '').join('')) : [];
    const xmlRows = tags(sheet, 'row');
    if (xmlRows.length > 5001) throw new Error('Importe no máximo 5.000 linhas por arquivo.');
    const rows = [];
    for (const xmlRow of xmlRows) {
      const row = [];
      let position = 0;
      for (const cell of tags(xmlRow, 'c')) {
        const explicit = columnIndex(cell.getAttribute('r') || '');
        if (explicit >= 0) position = explicit;
        if (position > 60) { position++; continue; }
        const type = cell.getAttribute('t') || '';
        const value = firstTag(cell, 'v')?.textContent || '';
        if (type === 's') row[position] = shared[Number(value)] || '';
        else if (type === 'inlineStr') row[position] = tags(cell, 't').map(t => t.textContent || '').join('');
        else if (type === 'e') row[position] = '';
        else row[position] = value;
        position++;
      }
      if (row.some(v => String(v || '').trim())) rows.push(row);
    }
    return rows;
  }

  async function readSpreadsheet(file) {
    if (!file || file.size > LIMIT) throw new Error('Escolha uma planilha de até 8 MB.');
    const filename = file.name || '';
    if (/\.csv$/i.test(filename)) return csvRows(await file.text());
    if (/\.xlsx$/i.test(filename)) return xlsxRows(file);
    throw new Error('Use um arquivo Excel (.xlsx) ou CSV (.csv).');
  }
  window.RumoSpreadsheetImport = {readSpreadsheet};
})();