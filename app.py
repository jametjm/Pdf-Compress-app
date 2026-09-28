import io
import os
import shutil
import tempfile
import zipfile
import fitz  # PyMuPDF
from PIL import Image
import streamlit as st

# --- 1. ตั้งค่า Page Config (ต้องอยู่บรรทัดแรกสุดของ Streamlit commands) ---
st.set_page_config(
    page_title="PDF Compressor Tool",
    page_icon="📄",
    layout="centered",
)


# --- 2. ฟังก์ชันตรวจสอบรหัสผ่าน (Authentication) ---
def check_password():
    """ส่งคืน True หากผู้ใช้ใส่รหัสผ่านถูกต้อง"""

    def password_entered():
        if st.session_state["password_input"] == "1234":
            st.session_state["password_correct"] = True
            del st.session_state[
                "password_input"
            ]  # ลบข้อมูลรหัสออกจาก session เพื่อความปลอดภัย
        else:
            st.session_state["password_correct"] = False

    # ถ้าเคยเข้าใช้งานสำเร็จแล้ว
    if st.session_state.get("password_correct", False):
        return True

    # แสดงหน้าจอ Login
    st.title("🔒 เข้าสู่ระบบใช้งานโปรแกรม")
    st.write("กรุณากรอกรหัสผ่านเพื่อเข้าใช้งานโปรแกรมบีบอัด PDF")

    st.text_input(
        "รหัสผ่าน (Password)",
        type="password",
        on_change=password_entered,
        key="password_input",
    )

    if "password_correct" in st.session_state:
        if not st.session_state["password_correct"]:
            st.error("❌ รหัสผ่านไม่ถูกต้อง กรุณาลองใหม่อีกครั้ง")

    return False


# หากตรวจสอบรหัสผ่านไม่ผ่าน ให้หยุดการทำงานตรงนี้ทันที
if not check_password():
    st.stop()


# --- 3. ฟังก์ชันประมวลผลบีบอัด PDF ---
def compress_pdf_file(
    pdf_bytes, filename, max_size=1280, quality=60, progress_bar=None
):
    """ฟังก์ชันประมวลผลบีบอัด PDF รายไฟล์"""
    # สร้างโฟลเดอร์ชั่วคราวใน RAM/Temp System
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_split_pdf = os.path.join(temp_dir, "1_split")
        temp_pics = os.path.join(temp_dir, "2_pics")
        temp_resized_pics = os.path.join(temp_dir, "3_resized")
        temp_compressed_pages = os.path.join(temp_dir, "4_compressed")

        for f in [
            temp_split_pdf,
            temp_pics,
            temp_resized_pics,
            temp_compressed_pages,
        ]:
            os.makedirs(f, exist_ok=True)

        # 1) แยกหน้า
        src_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        total_pages = len(src_doc)

        for page_num in range(total_pages):
            new_doc = fitz.open()
            new_doc.insert_pdf(src_doc, from_page=page_num, to_page=page_num)
            new_doc.save(
                os.path.join(temp_split_pdf, f"page_{page_num + 1}.pdf")
            )
            new_doc.close()
        src_doc.close()

        # 2) Convert PDF เป็น Image
        for pdf_file in sorted(os.listdir(temp_split_pdf)):
            if pdf_file.endswith(".pdf"):
                pdf_path = os.path.join(temp_split_pdf, pdf_file)
                doc = fitz.open(pdf_path)
                page = doc.load_page(0)
                pix = page.get_pixmap(dpi=120)
                pic_name = os.path.splitext(pdf_file)[0] + ".png"
                pix.save(os.path.join(temp_pics, pic_name))
                doc.close()

        # 3) Resize & Compress Image
        for pic_file in sorted(os.listdir(temp_pics)):
            if pic_file.lower().endswith(".png"):
                filepath = os.path.join(temp_pics, pic_file)
                try:
                    with Image.open(filepath) as img:
                        img.thumbnail((max_size, max_size))
                        img = img.convert("RGB")
                        output_jpg_name = (
                            os.path.splitext(pic_file)[0] + ".jpg"
                        )
                        output_jpg_path = os.path.join(
                            temp_resized_pics, output_jpg_name
                        )
                        img.save(
                            output_jpg_path,
                            "JPEG",
                            optimize=True,
                            quality=quality,
                        )
                except Exception as e:
                    st.error(f"Error sizing {pic_file}: {e}")

        # 4) Convert รูปกลับเป็น PDF หน้าเดี่ยว
        for jpg_file in sorted(os.listdir(temp_resized_pics)):
            if jpg_file.lower().endswith(".jpg"):
                img_path = os.path.join(temp_resized_pics, jpg_file)
                final_pdf_name = os.path.splitext(jpg_file)[0] + ".pdf"
                final_pdf_path = os.path.join(
                    temp_compressed_pages, final_pdf_name
                )
                with Image.open(img_path) as img:
                    img.save(final_pdf_path, "PDF")

        # 5) รวมไฟล์กลับ
        merged_doc = fitz.open()
        page_num = 1
        while True:
            expected_page_path = os.path.join(
                temp_compressed_pages, f"page_{page_num}.pdf"
            )
            if os.path.exists(expected_page_path):
                page_doc = fitz.open(expected_page_path)
                merged_doc.insert_pdf(page_doc)
                page_doc.close()
                page_num += 1
            else:
                break

        # บันทึกออกเป็น Bytes
        out_buffer = io.BytesIO()
        merged_doc.save(out_buffer, garbage=4, deflate=True)
        merged_doc.close()
        out_buffer.seek(0)
        return out_buffer.getvalue()


# --- 4. ส่วนแสดงผล UI หลังผ่านการตรวจสอบรหัสผ่านแล้ว ---
st.title("📄 PDF Compressor Web App")
st.write("เครื่องมือบีบอัดไฟล์ PDF ด้วยเทคนิค Convert Page-to-Image")

# ส่วนแถบตั้งค่าข้างๆ (Sidebar Settings)
st.sidebar.header("⚙️ การตั้งค่าบีบอัด")
max_size = st.sidebar.slider(
    "ขนาดกว้าง/ยาวสูงสุด (Pixels)", 600, 2400, 1280, step=100
)
quality = st.sidebar.slider("คุณภาพรูปภาพ JPEG (Quality %)", 10, 95, 60, step=5)

# 1. ปุ่มเลือกไฟล์ (ให้ลากวางได้หลายไฟล์)
uploaded_files = st.file_uploader(
    "เลือกไฟล์ PDF ที่ต้องการบีบอัด (เลือกได้หลายไฟล์)",
    type=["pdf"],
    accept_multiple_files=True,
)

if uploaded_files:
    st.info(f"เลือกไฟล์ไว้ทั้งหมด {len(uploaded_files)} ไฟล์")

    if st.button("🚀 เริ่มบีบอัดไฟล์ทั้งหมด", type="primary"):
        processed_files = []
        progress_bar = st.progress(0)

        for idx, file in enumerate(uploaded_files):
            st.text(
                f"กำลังจัดการไฟล์ ({idx+1}/{len(uploaded_files)}): {file.name}"
            )

            # อ่านไฟล์เป็น Bytes
            pdf_bytes = file.read()

            # สั่งประมวลผล
            output_bytes = compress_pdf_file(
                pdf_bytes, file.name, max_size, quality
            )

            raw_name = os.path.splitext(file.name)[0]
            compressed_name = f"{raw_name}_compressed.pdf"

            processed_files.append((compressed_name, output_bytes))

            # อัปเดต Progress Bar
            progress_bar.progress((idx + 1) / len(uploaded_files))

        st.success("🎉 บีบอัดไฟล์เรียบร้อยแล้ว!")

        # ถ้ามีไฟล์เดียว ให้ปุ่มโหลด PDF ตรงๆ
        if len(processed_files) == 1:
            file_name, file_bytes = processed_files[0]
            st.download_button(
                label=f"⬇️ ดาวน์โหลด {file_name}",
                data=file_bytes,
                file_name=file_name,
                mime="application/pdf",
            )
        # ถ้ามีหลายไฟล์ ให้มัดเป็น Zip ให้ดาวน์โหลด
        else:
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(
                zip_buffer, "w", zipfile.ZIP_DEFLATED
            ) as zip_file:
                for f_name, f_bytes in processed_files:
                    zip_file.writestr(f_name, f_bytes)
            zip_buffer.seek(0)

            st.download_button(
                label="⬇️ ดาวน์โหลดไฟล์ทั้งหมด (.ZIP)",
                data=zip_buffer,
                file_name="compressed_pdfs.zip",
                mime="application/zip",
            )
