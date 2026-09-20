const fs = require('fs');
const path = require('path');

let errors = [];
function assert(condition, msg) {
  if (!condition) {
    console.error('FAIL:', msg);
    errors.push(msg);
  } else {
    console.log('PASS:', msg);
  }
}

console.log('--- 1. Kiểm tra tài liệu đặc tả (docs/brand-identity.md) ---');
assert(fs.existsSync('docs/brand-identity.md'), 'docs/brand-identity.md tồn tại');
const spec = fs.readFileSync('docs/brand-identity.md', 'utf8');
assert(spec.includes('--brand-ivory') && spec.includes('#FBF8F3'), 'Tài liệu có token --brand-ivory (#FBF8F3)');
assert(spec.includes('--brand-sakura-soft') && spec.includes('#F5B8BA'), 'Tài liệu có token --brand-sakura-soft (#F5B8BA)');
assert(spec.includes('--brand-sakura-deep') && spec.includes('#DE7A85'), 'Tài liệu có token --brand-sakura-deep (#DE7A85)');
assert(spec.includes('--brand-gold-leaf') && spec.includes('#CFA348'), 'Tài liệu có token --brand-gold-leaf (#CFA348)');
assert(spec.includes('--brand-deep-berry') && spec.includes('#4A1521'), 'Tài liệu có token --brand-deep-berry (#4A1521)');
assert(spec.includes('TUYỆT ĐỐI KHÔNG') && spec.includes('lucide-react'), 'Tài liệu có quy định cấm dùng icon generic Lucide');

console.log('--- 2. Kiểm tra CSS Design Tokens (frontend/src/index.css) ---');
const css = fs.readFileSync('frontend/src/index.css', 'utf8');
assert(css.includes('--brand-ivory:       #fbf8f3;'), 'CSS có --brand-ivory');
assert(css.includes('--brand-sakura-soft: #f5b8ba;'), 'CSS có --brand-sakura-soft');
assert(css.includes('--brand-sakura-deep: #de7a85;'), 'CSS có --brand-sakura-deep');
assert(css.includes('--brand-gold-leaf:   #cfa348;'), 'CSS có --brand-gold-leaf');
assert(css.includes('--brand-deep-berry:  #4a1521;'), 'CSS có --brand-deep-berry');

console.log('--- 3. Kiểm tra file SVG Master (frontend/public/brand/) ---');
const svgFiles = [
  'microsched-mark.svg',
  'mimi-idle.svg',
  'mimi-thinking.svg',
  'mimi-executing.svg',
  'mimi-ready.svg',
  'orbit-blossom.svg'
];
for (const file of svgFiles) {
  const p = path.join('frontend', 'public', 'brand', file);
  assert(fs.existsSync(p), file + ' tồn tại trong frontend/public/brand/');
  const content = fs.readFileSync(p, 'utf8');
  const normalizedContent = content.trim();
  assert(normalizedContent.startsWith('<svg') && normalizedContent.endsWith('</svg>'), file + ' là file SVG hợp lệ');
  assert(content.includes('viewBox='), file + ' có thuộc tính viewBox');
  assert(content.includes('#CFA348'), file + ' chứa màu vàng kim (#CFA348)');
}

console.log('--- 4. Kiểm tra React Components (frontend/src/components/brand/) ---');
const brandComponents = [
  'MimiAvatar.tsx',
  'BrandLogo.tsx',
  'OrbitIndicator.tsx',
  'index.ts'
];
for (const comp of brandComponents) {
  const p = path.join('frontend', 'src', 'components', 'brand', comp);
  assert(fs.existsSync(p), comp + ' tồn tại trong frontend/src/components/brand/');
}

const mimiCode = fs.readFileSync('frontend/src/components/brand/MimiAvatar.tsx', 'utf8');
assert(!mimiCode.includes('lucide'), 'MimiAvatar KHÔNG import hay dùng icon Lucide');
assert(mimiCode.includes('data-testid="mimi-avatar"'), 'MimiAvatar có data-testid chuẩn');
assert(mimiCode.includes('idle') && mimiCode.includes('thinking') && mimiCode.includes('executing') && mimiCode.includes('ready'), 'MimiAvatar hỗ trợ đủ 4 trạng thái runtime');
assert(mimiCode.includes('aria-label'), 'MimiAvatar hỗ trợ aria-label trợ năng');

const logoCode = fs.readFileSync('frontend/src/components/brand/BrandLogo.tsx', 'utf8');
assert(logoCode.includes('data-testid="brand-logo"'), 'BrandLogo có data-testid chuẩn');
assert(logoCode.includes('Plan · Progress · Bloom'), 'BrandLogo chứa khẩu hiệu chuẩn');
assert(logoCode.includes('micro') && logoCode.includes('Sched'), 'BrandLogo chứa wordmark chuẩn');

const orbitCode = fs.readFileSync('frontend/src/components/brand/OrbitIndicator.tsx', 'utf8');
assert(orbitCode.includes('data-testid="orbit-indicator"'), 'OrbitIndicator có data-testid chuẩn');
assert(orbitCode.includes('standby') && orbitCode.includes('pulse') && orbitCode.includes('active') && orbitCode.includes('complete'), 'OrbitIndicator hỗ trợ đủ 4 trạng thái');

if (errors.length > 0) {
  console.error('\nTỔNG KẾT: CÓ ' + errors.length + ' LỖI CẦN KHẮC PHỤC!');
  process.exit(1);
} else {
  console.log('\nTỔNG KẾT: TẤT CẢ 26 HẠNG MỤC KIỂM TRA ĐỀU ĐẠT CHUẨN 100%!');
}
