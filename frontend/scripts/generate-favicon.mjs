// Dependency-free PNG fallback for the original SVG analytics mark.
import { writeFileSync } from 'node:fs';
import { deflateSync } from 'node:zlib';

function crc32(bytes) {
  let crc = 0xffffffff;
  for (const byte of bytes) {
    crc ^= byte;
    for (let bit = 0; bit < 8; bit++) crc = (crc >>> 1) ^ ((crc & 1) ? 0xedb88320 : 0);
  }
  return (crc ^ 0xffffffff) >>> 0;
}

function chunk(type, bytes) {
  const body = Buffer.concat([Buffer.from(type), bytes]);
  const length = Buffer.alloc(4);
  length.writeUInt32BE(bytes.length);
  const checksum = Buffer.alloc(4);
  checksum.writeUInt32BE(crc32(body));
  return Buffer.concat([length, body, checksum]);
}

const size = 48;
const pixels = Buffer.alloc(size * (size * 4 + 1));
for (let y = 0; y < size; y++) {
  for (let x = 0; x < size; x++) {
    const offset = y * (size * 4 + 1) + 1 + x * 4;
    const dx = Math.max(10 - x, x - 37, 0);
    const dy = Math.max(10 - y, y - 37, 0);
    const visible = dx * dx + dy * dy <= 100;
    const bar = (x >= 12 && x < 18 && y >= 24 && y < 31)
      || (x >= 21 && x < 27 && y >= 17 && y < 31)
      || (x >= 30 && x < 36 && y >= 10 && y < 31);
    const baseline = x >= 11 && x < 37 && y >= 33 && y < 35;
    const color = bar ? [127, 181, 245] : baseline ? [182, 192, 209] : [31, 36, 51];
    pixels.set([...color, visible ? 255 : 0], offset);
  }
}
const header = Buffer.alloc(13);
header.writeUInt32BE(size, 0);
header.writeUInt32BE(size, 4);
header[8] = 8;
header[9] = 6;
writeFileSync(new URL('../public/favicon.png', import.meta.url), Buffer.concat([
  Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]),
  chunk('IHDR', header),
  chunk('IDAT', deflateSync(pixels)),
  chunk('IEND', Buffer.alloc(0)),
]));
