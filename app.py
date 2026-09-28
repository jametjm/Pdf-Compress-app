import io
import os
import shutil
import tempfile
import zipfile
from PIL import Image
import fitz  # PyMuPDF
import streamlit as st


def compress_pdf_file(
    pdf_bytes,
    filename,
    max_size=1280,
    quality=60,
    password="1234",
    progress_bar=None,
):
    """ฟังก์ชันประมวลผลบีบอัด PDF รายไฟล์ พร้อมตั้งรหัสผ่านล็อกไฟล์"""
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

        # บันทึกออกเป็น Bytes พร้อมใส่ Password ล็อกไฟล์
        out_buffer = io.BytesIO()
        if password:
            # ใช้การเข้ารหัส AES-256 (PDF_ENCRYPT_AES_256) และตั้งค่า user_pw / owner_pw
            merged_doc.save(
                out_buffer,
                garbage=4,
                deflate=True,
                encryption=fitz.PDF_ENCRYPT_AES_256,
                user_pw=password,
                owner_pw=password,
            )
        else:
            merged_doc.save(out_buffer, garbage=4, deflate=True)

        merged_doc.close()
        out_buffer.seek(0)
        return out_buffer.getvalue()


# --- หน้าตา UI ของ Streamlit ---
st.set_page_config(
    page_title="PDF Compressor Tool", page_icon="📄", layout="centered"
)

st.title("📄 PDF Compressor Web App")
st.write("เครื่องมือบีบอัดไฟล์ PDF พร้อมระบบใส่รหัสผ่านป้องกันไฟล์")

# ส่วนแถบตั้งค่าข้างๆ (Sidebar Settings)
st.sidebar.header("⚙️ การตั้งค่าบีบอัด")
max_size = st.sidebar.slider(
    "ขนาดกว้าง/ยาวสูงสุด (Pixels)", 600, 2400, 1280, step=100
)
quality = st.sidebar.slider("คุณภาพรูปภาพ JPEG (Quality %)", 10, 95, 60, step=5)

# เพิ่มช่องสำหรับกรอก/ตั้งค่า Password
st.sidebar.header("🔒 การตั้งค่ารหัสผ่าน")
pdf_password = st.sidebar.text_input(
    "รหัสผ่านล็อกไฟล์ PDF Output", value="1234", type="password"
)

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
            st.text(f"กำลังจัดการไฟล์ ({idx+1}/{len(uploaded_files)}): {file.name}")

            # อ่านไฟล์เป็น Bytes
            pdf_bytes = file.read()

            # สั่งประมวลผล (ส่งค่า password กำหนดไว้ลงไปด้วย)
            output_bytes = compress_pdf_file(
                pdf_bytes,
                file.name,
                max_size=max_size,
                quality=quality,
                password=pdf_password,
            )

            raw_name = os.path.splitext(file.name)[0]
            compressed_name = f"{raw_name}_compressed.pdf"

            processed_files.append((compressed_name, output_bytes))

            # อัปเดต Progress Bar
            progress_bar.progress((idx + 1) / len(uploaded_files))

        st.success("🎉 บีบอัดและใส่รหัสผ่านเรียบร้อยแล้ว!")

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
