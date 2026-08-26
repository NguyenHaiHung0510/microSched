# QA Spec - Browser acceptance cho local QA auth + DB guard (PR #175)

Trang thai tai lieu: SPEC CHO THUC THI. Moi muc chua chay ghi ro NOT RUN.
Thuc thi du kien: Gemini 3.7 qua Chrome MCP, UU TIEN cua so Chrome an danh
(khong dung profile Chrome that cua chu; neu ky thuat khong cho phep thi ghi
ro vao receipt va xin xac nhan truoc khi dung profile khac).

## Dieu kien tien de

- PR #175 da merge vao develop VA deploy production hoan tat (kiem /api/readyz
  tren fly.dev tra db=up dung commit moi). Endpoint /auth/dev-session chi ton
  tai o ban code nay.
  Bat buoc ghi receipt: gia tri exact cua readyz.commit va db=up.
  Bat buoc ghi receipt: gia tri exact cua readyz.commit va db=up.
- Local backend chay duoc: APP_ENV=local, NEON_DEVELOP_BRANCH_KEY tro nhanh Neon
  develop (chu sync tay tu prod truoc khi QA), uvicorn lang nghe 127.0.0.1:8000;
  frontend Vite o localhost:5173 proxy sang backend.
- KHONG doc, sao chep hay hien thi noi dung backend/.env. Chi chu so huu tu
  dam bao bien moi truong; agent chi quan sat hanh vi HTTP/trinh duyet.

## Ca kiem thu

### TC1 - Guard chan local tro thang production (fail-closed)

Cach chay: tam go branch key (hoac dat DATABASE_URL ve URL prod), khoi dong
uvicorn local, ky vong process thoat ngay voi ValidationError chua chuoi
"refuses to start with the production DATABASE_URL". Ghi lai stderr 5 dong cuoi.
Sau do khoi phuc cau hinh develop NGAY LAP TUC.
Cac buoc mo rong (mo phong dung cac case guard moi, khong can mang):
- loopback DATABASE_URL + branch key tro prod: tu choi voi
  "production DATABASE_URL";
- khong co DATABASE_URL + branch key tro prod + NEON_OWNER_URL=prod:
  tu choi voi "production DATABASE_URL";
- co branch key nhung thieu NEON_OWNER_URL/NEON_MIGRATOR_URL:
  tu choi voi "requires at least one production reference";
- DATABASE_URL remote (vi du staging) khong duoc reference nao xac nhan:
  tu choi voi "only accepts a loopback".
Cac buoc mo rong (mo phong dung cac case guard moi, khong can mang):
- loopback DATABASE_URL + branch key tro prod: tu choi voi
  "production DATABASE_URL";
- khong co DATABASE_URL + branch key tro prod + NEON_OWNER_URL=prod:
  tu choi voi "production DATABASE_URL";
- co branch key nhung thieu NEON_OWNER_URL/NEON_MIGRATOR_URL:
  tu choi voi "requires at least one production reference";
- DATABASE_URL remote (vi du staging) khong duoc reference nao xac nhan:
  tu choi voi "only accepts a loopback".
Buoc con (chi chay khi chu dong y): ALLOW_PROD_DB_IN_LOCAL=true cho server boot
duoc - luu y no ket noi prod that tu may local.

### TC2 - dev-session hoat dong o local qua loopback

Mo http://localhost:5173/auth/dev-session (hoac :8000 truc tiep). Ky vong:
HTTP 303 redirect ve /, cookie ms_session duoc dat voi HttpOnly, SameSite=Lax,
Secure TAT (local http), UI trang chu hien user owner@test.local voi du lieu GIA
cua nhanh develop. Chu xac nhan buoc du lieu gia nay - agent chi chup bang chung.

### TC3 - dev-session 404 khi APP_ENV=production (deploy that)

Go https://microsched.fly.dev/auth/dev-session (khong dang nhap gi truoc do).
Ky vong: 404 "Not available", khong co cookie nao duoc dat. Neu tra HTML SPA
cua frontend thi ghi ro hien tuong va danh dau CHUA VERIFY o tang app.

### TC4 - Logout xoa session ngay lap tuc

Sau TC2: bam Dang xuat trong UI. Ky vong: 204, cookie bi xoa, reload trang
khong con trang thai dang nhap; goi lai mot API protected bat ky tra 401.

### TC5 - Truy cap dev-session tu IP ngoai loopback (negative)

NOT RUN by design: backend bind 127.0.0.1 theo tien de, safety boundary chi
cho phep localhost/fly.dev nen case LAN khong bao gio duoc thuc thi trong QA;
case da duoc test don vi test_dev_session_is_unreachable_from_non_loopback phu.

## Rang buoc an toan khi thuc thi

- Chi dieu huong toi localhost/127.0.0.1 va microsched.fly.dev; khong mo tab khac.
- Khong doc cookie store, autofill, history, password cua trinh duyet.
- Khong gan dia chi email ca nhan that vao receipt; chi viet vai owner@test.local
  hoac "tai khoan that" truu tuong.
- Screenshot cat gon, soi truoc khi dinh kem (khong lo bookmark/avatar).
- Xong viec: dang xuat, dong tab, khong de lai phien nao.

## Bien lai can thu

- TC1: stderr guard (da chay / NOT RUN + ly do).
- TC2: screenshot trang chu sau redirect + dong 303; cookie flags chi ghi TEN
  cookie va thuoc tinh (HttpOnly/SameSite/Secure) - TUYET DOI redact gia tri
  token, khong chup nguyen header Set-Cookie vao artifact.
- TC3: status code + body dau tien tu fly.dev + readyz.commit exact + db=up.
- TC5: status code hoac NOT RUN.
- Nhan dinh chu ve "du lieu GIA cua nhanh develop" o TC2 la BAT BUOC de dong
  muc nay (agent khong tu biet du lieu nao la that).
