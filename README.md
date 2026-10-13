# OEE Dashboard (Streamlit)

Dashboard OEE, Time Loss และ Waste ที่ดึงข้อมูลจาก Google Sheet "ME Order" อัตโนมัติ (อัปเดตทุก 10 นาที หรือกดปุ่ม "ดึงข้อมูลใหม่ตอนนี้")

## ไฟล์ในโปรเจกต์
| ไฟล์ | หน้าที่ |
|---|---|
| `app.py` | หน้าจอ dashboard (แท็บ OEE แยกเครื่อง / OEE รวมรายเดือน / Time Loss / Waste / ตารางข้อมูล) |
| `data.py` | ดึงข้อมูลจากชีตและคำนวณ A, P, Q, OEE |
| `assets/makorn_logo.jpg` | โลโก้บริษัท (แสดงที่หัวหน้าและแถบด้านซ้าย) |
| `requirements.txt` | รายชื่อแพ็กเกจที่ Streamlit Cloud ต้องติดตั้ง |
| `.streamlit/secrets.toml.example` | ตัวอย่างค่าที่ต้องใส่ใน Secrets |

## ข้อมูลที่ใช้
- **OEE_DATA** (ข้อมูลเก่า) + **OEE_FORM** (ข้อมูลจากฟอร์ม) รวมกัน
- **OEE_Total** (ถ้ามี) แสดงในแท็บ "OEE รวมรายเดือน" ตามตัวเลขในชีตตรงๆ
- **TimeLoss** (รหัส → สาเหตุ → กลุ่ม หยุดตามแผน/A/P) และ **Waste** (รหัสของเสีย → สาเหตุ)
- ตำแหน่งคอลัมน์ตั้งไว้ใน `COLS` ด้านบนของ `data.py` ถ้าย้ายคอลัมน์ในชีต แก้ตัวอักษรคอลัมน์ที่นั่นที่เดียว

## วิธี Deploy

### 1. เลือกวิธีให้แอปอ่านชีต (เลือกอย่างใดอย่างหนึ่ง)
**ก. แชร์ชีตแบบมีลิงก์ (ง่ายที่สุด)**
Google Sheets → Share → General access: **Anyone with the link → Viewer**
ข้อควรรู้: ใครมีลิงก์ชีตก็เปิดอ่านได้

**ข. Service Account (แนะนำ ชีตไม่ต้องเปิดสาธารณะ)**
1. ไปที่ https://console.cloud.google.com → สร้าง Project
2. APIs & Services → Library → เปิด **Google Sheets API** และ **Google Drive API**
3. IAM & Admin → Service Accounts → Create → เข้าไปที่ account → Keys → Add key → JSON (จะได้ไฟล์ .json)
4. เปิดชีต → Share → ใส่อีเมล `...@...iam.gserviceaccount.com` ให้สิทธิ์ **Viewer**
5. นำค่าจากไฟล์ JSON ไปใส่ใน Secrets ตามรูปแบบใน `.streamlit/secrets.toml.example`

### 2. อัปโหลดขึ้น GitHub
1. https://github.com/new → ตั้งชื่อ repo เช่น `oee-dashboard` (เลือก Private ได้)
2. กด "uploading an existing file" → ลากไฟล์ทั้งหมดในโฟลเดอร์นี้ (รวมโฟลเดอร์ `.streamlit`) → Commit

### 3. Deploy บน Streamlit Community Cloud
1. https://share.streamlit.io → Sign in with GitHub
2. Create app → เลือก repo `oee-dashboard`, branch `main`, Main file `app.py`
3. Advanced settings → **Secrets**: วาง `sheet_id = "..."` (และส่วน `[gcp_service_account]` ถ้าใช้วิธี ข.)
4. Deploy → รอ 2–3 นาที

### 4. จำกัดคนดู (ถ้าต้องการ)
ในหน้าแอปบน Streamlit Cloud → Settings → Sharing → ตั้งให้เฉพาะอีเมลที่เชิญเท่านั้นที่เปิดได้

## วิธีคิด
- Planned time = ชม.ทำงาน − หยุดตามแผน · Run time = Planned time − เสีย A
- Availability = Run time ÷ Planned time · Performance = Ideal time ÷ Run time · Quality = kg ดี ÷ (kg ดี + ของเสีย kg) (ถ้าไม่มี kg ดี = 100%)
- ค่ารวมหลายเดือน/หลายเครื่องคำนวณจาก **ผลรวมชั่วโมงและ kg** ไม่ใช่ค่าเฉลี่ยของ %
- ค่าเริ่มต้นไม่รวม SF ที่ขึ้นต้นด้วย IS (รวมทุกเครื่อง รวม DT) ปิดได้ที่ตัวกรองด้านซ้าย
- DT ไม่ได้บันทึก kg ผลผลิตดี จึงคิด Quality ของ DT = 100%
- ชม.ทำงานของข้อมูลจากฟอร์มคิดจาก End time − Start time โดยตรง
