# GO-LIVE CHECKLIST (Production) — Face Attendance (Windows)

เวอร์ชันสำหรับใช้งานหน้างานได้ทันที  
แนะนำ deploy จาก Git tag/release

---

## 0) ข้อมูลที่ต้องกรอกก่อนเริ่ม

- **Server:** ..........................................
- **Path:** `D:\face_attendance_pg`
- **Release target (Tag):** `v........`
- **Current running tag/commit:** ........................
- **Change window:** .......... ถึง ..........
- **Operator:** ........................
- **Approver:** ........................

---

## 1) Pre-check (ก่อนตัดขึ้นจริง)

### 1.1 Source/Release readiness
- [ ] PR เข้า `main` ผ่าน review แล้ว
- [ ] Tag release ถูกต้อง (เช่น `v0.2.0`)
- [ ] Release notes พร้อม
- [ ] มี rollback target ชัดเจน (tag ก่อนหน้า เช่น `v0.1.0`)

### 1.2 Infra/Service readiness
- [ ] Service ทำงานปกติ:
  - [ ] `FaceAttendance-Backend` = Running
  - [ ] `FaceAttendance-Caddy` = Running
  - [ ] Worker service = Running
- [ ] Port/URL ใช้งานได้:
  - [ ] `https://<server>:8443/health` ตอบ `{"ok":true}`
- [ ] พื้นที่ดิสก์พอ (>20% แนะนำ)
- [ ] เวลาเครื่อง/Timezone ถูกต้อง (`Asia/Bangkok`)

### 1.3 Config/Security
- [ ] `.env` production ครบ (DB, API key, camera)
- [ ] ตรวจว่า **ไม่ commit secret** ลง Git
- [ ] Caddy ชี้ backend port ถูกต้อง (`8010`)
- [ ] HTTP redirect → HTTPS ทำงาน (ถ้าตั้งไว้)

### 1.4 Backup/Snapshot
- [ ] สำรองไฟล์ config:
  - [ ] `.env`
  - [ ] `C:\Caddy\Caddyfile`
- [ ] สำรอง DB (หรือมี PITR)
- [ ] จด current commit/tag ก่อน deploy

---

## 2) Cutover (ขั้นตอนขึ้นระบบจริง)

> แนะนำทำใน maintenance window

### 2.1 Freeze & fetch
- [ ] แจ้งผู้ใช้งาน “เริ่ม deploy”
- [ ] เปิด PowerShell (Run as Admin)

```powershell
cd D:\face_attendance_pg
git fetch --all --tags
git checkout <TARGET_TAG>   # เช่น v0.2.0
git rev-parse --short HEAD
```

### 2.2 Install dependencies
```powershell
cd D:\face_attendance_pg\backend
.\.venv\Scripts\pip install -r requirements.txt

cd D:\face_attendance_pg\worker
.\.venv\Scripts\pip install -r requirements.txt
```

### 2.3 Reload proxy/config (ถ้ามีเปลี่ยน)
```powershell
C:\Caddy\caddy.exe reload --config C:\Caddy\Caddyfile
```

### 2.4 Restart services
```powershell
Restart-Service FaceAttendance-Backend
Restart-Service FaceAttendance-Caddy
# ถ้ามี worker service แยก:
# Restart-Service FaceAttendance-Worker
```

### 2.5 Smoke test ทันที
- [ ] `https://<server>:8443/health` = ok
- [ ] เข้า login ได้
- [ ] หน้า `/schedule/matrix` เปิดได้
- [ ] หน้า `/employees/<id>/enroll` เปิดได้
- [ ] worker มองเห็นกล้อง online

---

## 3) Post-check (หลังขึ้นระบบ)

### 3.1 Functional checks
- [ ] Import schedule จากไฟล์ (sheet `Approve`) สำเร็จ
- [ ] หน้า Schedule Matrix:
  - [ ] สี status ครบ
  - [ ] วันนี้เด่น + animation
  - [ ] weekend/holiday แสดงถูก
  - [ ] toggle ทำงาน
- [ ] Enroll:
  - [ ] webcam ใช้ได้บน HTTPS
  - [ ] import รูปหลายไฟล์ได้
  - [ ] finalize ได้เมื่อครบเงื่อนไข
- [ ] Camera Monitor:
  - [ ] กล้องครบ
  - [ ] heartbeat อัปเดต
  - [ ] preview อัปเดต

### 3.2 Data integrity checks
- [ ] ไม่มี error ใหม่ใน log หลัง deploy 10–15 นาที
- [ ] attendance insert ได้ปกติ
- [ ] schedule_assignments เดือนปัจจุบันครบ

### 3.3 Performance/basic stability
- [ ] หน้าโหลดไม่ช้าผิดปกติ
- [ ] CPU/RAM ไม่พุ่งผิดปกติ
- [ ] Service ไม่ restart loop

### 3.4 Sign-off
- [ ] ผู้ใช้งาน key user ยืนยันใช้งานได้
- [ ] ปิด change window
- [ ] บันทึก deployment record

---

## 4) Rollback Plan (ถ้าเกิดปัญหา)

### Trigger rollback เมื่อ:
- [ ] health check fail ต่อเนื่อง
- [ ] หน้าใช้งานหลักล่ม
- [ ] attendance/schedule เขียนข้อมูลผิด
- [ ] worker กล้องตกทั้งหมดและแก้เร็วไม่ได้

### ขั้นตอน rollback
```powershell
cd D:\face_attendance_pg
git fetch --all --tags
git checkout <PREVIOUS_TAG>   # เช่น v0.1.0

cd D:\face_attendance_pg\backend
.\.venv\Scripts\pip install -r requirements.txt

cd D:\face_attendance_pg\worker
.\.venv\Scripts\pip install -r requirements.txt

Restart-Service FaceAttendance-Backend
Restart-Service FaceAttendance-Caddy
# Restart-Service FaceAttendance-Worker
```

### Verify หลัง rollback
- [ ] `https://<server>:8443/health` = ok
- [ ] หน้า/ฟังก์ชันหลักใช้งานกลับมาปกติ
- [ ] แจ้งผู้ใช้ว่า rollback สำเร็จ

---

## 5) คำสั่งสรุปที่ใช้บ่อย (Quick Commands)

```powershell
# ดูสถานะ service
Get-Service FaceAttendance-Backend,FaceAttendance-Caddy

# เช็ค health
curl.exe -k https://<server>:8443/health

# ดู tag
git tag --list

# ดู commit ปัจจุบัน
git rev-parse --short HEAD
```
