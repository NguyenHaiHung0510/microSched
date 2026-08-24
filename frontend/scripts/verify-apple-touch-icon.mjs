import fs from 'node:fs'
import path from 'node:path'
import zlib from 'node:zlib'

const root = process.cwd()
const html = fs.readFileSync(path.join(root, 'index.html'), 'utf8')
const expectedLink = '<link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon-180x180.png" />'
if (!html.includes(expectedLink)) {
  throw new Error(`index.html thiếu link chính xác: ${expectedLink}`)
}

const signature = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10])
const readPng = (file) => {
  const data = fs.readFileSync(file)
  if (!data.subarray(0, 8).equals(signature)) throw new Error(`${file}: không phải PNG`)
  let offset = 8
  let width
  let height
  let bitDepth
  let colorType
  const idat = []
  while (offset < data.length) {
    const length = data.readUInt32BE(offset)
    const type = data.toString('ascii', offset + 4, offset + 8)
    const body = data.subarray(offset + 8, offset + 8 + length)
    offset += length + 12
    if (type === 'IHDR') {
      width = body.readUInt32BE(0)
      height = body.readUInt32BE(4)
      bitDepth = body[8]
      colorType = body[9]
      if (body[12] !== 0) throw new Error(`${file}: interlace không được hỗ trợ`)
    } else if (type === 'IDAT') {
      idat.push(body)
    } else if (type === 'IEND') {
      break
    }
  }
  if (width !== 180 || height !== 180 || bitDepth !== 8 || colorType !== 6) {
    throw new Error(`${file}: cần PNG RGBA 8-bit 180x180, nhận ${width}x${height}, depth=${bitDepth}, type=${colorType}`)
  }
  const raw = zlib.inflateSync(Buffer.concat(idat))
  const stride = width * 4
  const rowSize = stride + 1
  const pixels = Buffer.alloc(height * stride)
  const prior = Buffer.alloc(stride)
  for (let y = 0; y < height; y += 1) {
    const filter = raw[y * rowSize]
    const row = raw.subarray(y * rowSize + 1, (y + 1) * rowSize)
    const output = pixels.subarray(y * stride, (y + 1) * stride)
    for (let x = 0; x < stride; x += 1) {
      const left = x >= 4 ? output[x - 4] : 0
      const up = prior[x]
      const upperLeft = x >= 4 ? prior[x - 4] : 0
      if (filter === 0) output[x] = row[x]
      else if (filter === 1) output[x] = (row[x] + left) & 255
      else if (filter === 2) output[x] = (row[x] + up) & 255
      else if (filter === 3) output[x] = (row[x] + Math.floor((left + up) / 2)) & 255
      else if (filter === 4) {
        const p = left + up - upperLeft
        const pa = Math.abs(p - left)
        const pb = Math.abs(p - up)
        const pc = Math.abs(p - upperLeft)
        output[x] = (row[x] + (pa <= pb && pa <= pc ? left : pb <= pc ? up : upperLeft)) & 255
      } else throw new Error(`${file}: PNG filter ${filter} không hợp lệ`)
    }
    output.copy(prior)
  }
  for (let i = 3; i < pixels.length; i += 4) {
    if (pixels[i] !== 255) throw new Error(`${file}: alpha không opaque tại pixel ${Math.floor(i / 4)}`)
  }
}

const icon = 'apple-touch-icon-180x180.png'
const source = path.join(root, 'public', icon)
const built = path.join(root, 'dist', icon)
if (!fs.existsSync(source)) throw new Error(`thiếu public/${icon}`)
if (!fs.existsSync(built)) throw new Error(`build không chứa ${icon}`)
readPng(source)
readPng(built)
console.log(`PASS apple-touch-icon: link + ${icon} source/dist đều 180x180 RGBA opaque`)
