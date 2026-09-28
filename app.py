import io
import os
import tempfile
import zipfile
import fitz  # PyMuPDF
from PIL import Image
import streamlit as st

# ==========================================
# 1. ระบบยืนยันตัวตน (Authentication)
# ==========================================
def check_password():
    """ตรวจสอบรหัสผ่านก่อนเข้าใช้งานแอป"""
    def password_entered():
        if st.session_state["password"] == "1234":
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # ลบรหัสออกจาก memory
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.set_page_config(page_title="ระบบล็อกอิน", page_icon="🔒")
        st.title("🔒 กรุณาใส่รหัสผ่านเพื่อเข้าใช้งาน")
        st.text_input(
            "Password", type="password", on_change=password_entered, key="password"
        )
        return False
    elif not st.session_state["password_correct"]:
        st.set_page_config(page_title="ระบบล็อกอิน", page_icon="🔒")
        st.title("🔒 กรุณาใส่รหัสผ่านเพื่อเข้าใช้งาน")
        st.text_input(
            "Password", type="password", on_change=password_entered, key="password"
        )
        st.error("❌ รหัสผ่านไม่ถูกต้อง กรุณาลองใหม่อีกครั้ง")
        return False
    else:
        return True


# ==========================================
# 2. ฟังก์ชันประมวลผล PDF Reducer (บีบอัด)
# ==========================================
def compress_pdf_file(pdf_bytes, filename, max_size=1280, quality=60):
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_split_pdf = os.path.join(temp_dir, "1_split")
        temp_pics = os.path.join(temp_dir, "2_pics")
        temp_resized_pics = os.path.join(temp_dir, "3_resized")
        temp_compressed_pages = os.path.join(temp_dir, "4_compressed")

        for f in [temp_split_pdf, temp_pics, temp_resized_pics, temp_compressed_pages]:
            os.makedirs(f, exist_ok=True)

        src_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        total_pages = len(src_doc)

        for page_num in range(total_pages):
            new_doc = fitz.open()
            new_doc.insert_pdf(src_doc, from_page=page_num, to_page=page_num)
            new_doc.save(os.path.join(temp_split_pdf, f"page_{page_num + 1}.pdf"))
            new_doc.close()
        src_doc.close()

        for pdf_file in sorted(os.listdir(temp_split_pdf)):
            if pdf_file.endswith(".pdf"):
                pdf_path = os.path.join(temp_split_pdf, pdf_file)
                doc = fitz.open(pdf_path)
                page = doc.load_page(0)
                pix = page.get_pixmap(dpi=120)
                pic_name = os.path.splitext(pdf_file)[0] + ".png"
                pix.save(os.path.join(temp_pics, pic_name))
                doc.close()

        for pic_file in sorted(os.listdir(temp_pics)):
            if pic_file.lower().endswith(".png"):
                filepath = os.path.join(temp_pics, pic_file)
                try:
                    with Image.open(filepath) as img:
                        img.thumbnail((max_size, max_size))
                        img = img.convert("RGB")
                        output_jpg_name = os.path.splitext(pic_file)[0] + ".jpg"
                        output_jpg_path = os.path.join(temp_resized_pics, output_jpg_name)
                        img.save(output_jpg_path, "JPEG", optimize=True, quality=quality)
                except Exception as e:
                    st.error(f"Error sizing {pic_file}: {e}")

        for jpg_file in sorted(os.listdir(temp_resized_pics)):
            if jpg_file.lower().endswith(".jpg"):
                img_path = os.path.join(temp_resized_pics, jpg_file)
                final_pdf_name = os.path.splitext(jpg_file)[0] + ".pdf"
                final_pdf_path = os.path.join(temp_compressed_pages, final_pdf_name)
                with Image.open(img_path) as img:
                    img.save(final_pdf_path, "PDF")

        merged_doc = fitz.open()
        page_num = 1
        while True:
            expected_page_path = os.path.join(temp_compressed_pages, f"page_{page_num}.pdf")
            if os.path.exists(expected_page_path):
                page_doc = fitz.open(expected_page_path)
                merged_doc.insert_pdf(page_doc)
                page_doc.close()
                page_num += 1
            else:
                break

        out_buffer = io.BytesIO()
        merged_doc.save(out_buffer, garbage=4, deflate=True)
        merged_doc.close()
        out_buffer.seek(0)
        return out_buffer.getvalue()


# ==========================================
# 3. ฟังก์ชันประมวลผล Image Reducer
# ==========================================
def compress_image_file(image_bytes, max_size=1280, quality=85):
    with Image.open(io.BytesIO(image_bytes)) as img:
        img.thumbnail((max_size, max_size))

        if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
            background = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode != "RGBA":
                img = img.convert("RGBA")
            background.paste(img, mask=img.split()[3])
            img = background
        else:
            img = img.convert("RGB")

        out_buffer = io.BytesIO()
        img.save(out_buffer, format="JPEG", optimize=True, quality=quality)
        out_buffer.seek(0)
        return out_buffer.getvalue()


# ==========================================
# 4. ฟังก์ชันประมวลผล PDF Splitter (แยกหน้า)
# ==========================================
def split_pdf_bytes(pdf_bytes, start_page, end_page):
    """แยกหน้า PDF ตามช่วงที่ผู้ใช้เลือก (PyMuPDF)"""
    src_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    total_pages = len(src_doc)

    # ปรับขอบเขตกรณีใส่นอกช่วง
    start_idx = max(0, start_page - 1)
    end_idx = min(total_pages - 1, end_page - 1)

    split_results = []  # [(filename, bytes)]

    for page_num in range(start_idx, end_idx + 1):
        new_doc = fitz.open()
        new_doc.insert_pdf(src_doc, from_page=page_num, to_page=page_num)

        out_buffer = io.BytesIO()
        new_doc.save(out_buffer)
        new_doc.close()
        out_buffer.seek(0)

        split_results.append((f"page_{page_num + 1}.pdf", out_buffer.getvalue()))

    src_doc.close()
    return split_results, total_pages


# ==========================================
# 5. หน้าแอปพลิเคชันหลัก (Main UI)
# ==========================================
def main_app():
    st.set_page_config(page_title="File Optimization Suite", page_icon="🛠️", layout="centered")

    st.sidebar.title("🛠️ เลือกแอปพลิเคชัน")
    app_choice = st.sidebar.radio(
        "ฟังก์ชันการทำงาน:",
        [
            "📄 PDF Reducer (ย่อ PDF)",
            "✂️ PDF Splitter (แยกหน้า PDF)",
            "🖼️ Picture Reducer (ย่อรูปภาพ)"
        ]
    )

    st.sidebar.markdown("---")
    if st.sidebar.button("🔒 ออกจากระบบ"):
        st.session_state["password_correct"] = False
        st.rerun()

    # --------------------------------------
    # APP 1: PDF Reducer
    # --------------------------------------
    if app_choice == "📄 PDF Reducer (ย่อ PDF)":
        st.title("📄 PDF Reducer")
        st.write("ลดขนาดไฟล์ PDF โดยแปลงแต่ละหน้าเป็นรูปภาพบีบอัดแล้วประกอบกลับ")

        st.sidebar.header("⚙️ ตั้งค่า PDF")
        max_size_pdf = st.sidebar.slider("ขนาดสูงสุด (Pixels)", 600, 2400, 1280, step=100, key="pdf_size")
        quality_pdf = st.sidebar.slider("คุณภาพ JPEG (%)", 10, 95, 60, step=5, key="pdf_qual")

        uploaded_pdfs = st.file_uploader("เลือกไฟล์ PDF (หลายไฟล์ได้)", type=["pdf"], accept_multiple_files=True, key="reducer_uploader")

        if uploaded_pdfs and st.button("🚀 เริ่มบีบอัด PDF ทั้งหมด", type="primary"):
            processed_files = []
            progress_bar = st.progress(0)

            for idx, file in enumerate(uploaded_pdfs):
                st.text(f"กำลังจัดการไฟล์ ({idx+1}/{len(uploaded_pdfs)}): {file.name}")
                pdf_bytes = file.read()
                out_bytes = compress_pdf_file(pdf_bytes, file.name, max_size_pdf, quality_pdf)
                
                raw_name = os.path.splitext(file.name)[0]
                processed_files.append((f"{raw_name}_compressed.pdf", out_bytes))
                progress_bar.progress((idx + 1) / len(uploaded_pdfs))

            st.success("🎉 บีบอัด PDF เรียบร้อย!")

            if len(processed_files) == 1:
                f_name, f_bytes = processed_files[0]
                st.download_button(f"⬇️ ดาวน์โหลด {f_name}", f_bytes, file_name=f_name, mime="application/pdf")
            else:
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                    for f_name, f_bytes in processed_files:
                        zf.writestr(f_name, f_bytes)
                zip_buffer.seek(0)
                st.download_button("⬇️ ดาวน์โหลดทั้งหมด (.ZIP)", zip_buffer, file_name="compressed_pdfs.zip", mime="application/zip")

    # --------------------------------------
    # APP 2: PDF Splitter
    # --------------------------------------
    elif app_choice == "✂️ PDF Splitter (แยกหน้า PDF)":
        st.title("✂️ PDF Splitter")
        st.write("แยกไฟล์ PDF ออกเป็นไฟล์ละ 1 หน้า โดยเลือกช่วงหน้าที่ต้องการแยกได้")

        uploaded_pdf = st.file_uploader("เลือกไฟล์ PDF ที่ต้องการแยกหน้า", type=["pdf"], key="splitter_uploader")

        if uploaded_pdf:
            pdf_bytes = uploaded_pdf.read()
            # ตรวจสอบจำนวนหน้าก่อน
            doc_preview = fitz.open(stream=pdf_bytes, filetype="pdf")
            total_p = len(doc_preview)
            doc_preview.close()

            st.info(f"📄 ไฟล์นี้มีทั้งหมด **{total_p}** หน้า")

            # ตัวเลือกกำหนดช่วงหน้า
            col1, col2 = st.columns(2)
            with col1:
                start_p = st.number_input("เริ่มต้นจากหน้า", min_value=1, max_value=total_p, value=1)
            with col2:
                end_p = st.number_input("ถึงหน้า", min_value=1, max_value=total_p, value=total_p)

            if start_p > end_p:
                st.warning("⚠️ หน้าเริ่มต้นต้องน้อยกว่าหรือเท่ากับหน้าสิ้นสุด")

            if st.button("✂️ เริ่มแยกหน้า PDF", type="primary", disabled=(start_p > end_p)):
                split_files, _ = split_pdf_bytes(pdf_bytes, int(start_p), int(end_p))
                raw_name = os.path.splitext(uploaded_pdf.name)[0]

                st.success(f"🎉 แยกหน้าเรียบร้อยทั้งหมด {len(split_files)} หน้า!")

                # ถ้าแยกหน้าเดียว มีปุ่มดาวน์โหลดไฟล์เดี่ยว
                if len(split_files) == 1:
                    f_name, f_bytes = split_files[0]
                    st.download_button(
                        label=f"⬇️ ดาวน์โหลด {raw_name}_{f_name}",
                        data=f_bytes,
                        file_name=f"{raw_name}_{f_name}",
                        mime="application/pdf"
                    )
                else:
                    # ถ้าหลายหน้า รวบรวมลง ZIP
                    zip_buffer = io.BytesIO()
                    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                        for f_name, f_bytes in split_files:
                            zf.writestr(f"{raw_name}_{f_name}", f_bytes)
                    zip_buffer.seek(0)

                    st.download_button(
                        label="⬇️ ดาวน์โหลดหน้าทั้งหมด (.ZIP)",
                        data=zip_buffer,
                        file_name=f"{raw_name}_split.zip",
                        mime="application/zip"
                    )

    # --------------------------------------
    # APP 3: Picture Reducer
    # --------------------------------------
    elif app_choice == "🖼️ Picture Reducer (ย่อรูปภาพ)":
        st.title("🖼️ Picture Reducer")
        st.write("ย่อขนาดและบีบอัดรูปภาพ (JPG, JPEG, PNG) ออกเป็นไฟล์ JPG")

        st.sidebar.header("⚙️ ตั้งค่า รูปภาพ")
        max_size_img = st.sidebar.slider("ขนาดสูงสุด (Pixels)", 400, 3840, 1280, step=80, key="img_size")
        quality_img = st.sidebar.slider("คุณภาพ JPEG (%)", 10, 100, 85, step=5, key="img_qual")

        uploaded_imgs = st.file_uploader("เลือกรูปภาพ JPG/PNG (หลายไฟล์ได้)", type=["jpg", "jpeg", "png"], accept_multiple_files=True, key="img_uploader")

        if uploaded_imgs and st.button("🚀 เริ่มย่อรูปภาพทั้งหมด", type="primary"):
            processed_files = []
            progress_bar = st.progress(0)

            for idx, file in enumerate(uploaded_imgs):
                st.text(f"กำลังย่อรูป ({idx+1}/{len(uploaded_imgs)}): {file.name}")
                img_bytes = file.read()
                out_bytes = compress_image_file(img_bytes, max_size_img, quality_img)
                
                raw_name = os.path.splitext(file.name)[0]
                processed_files.append((f"{raw_name}_resized.jpg", out_bytes))
                progress_bar.progress((idx + 1) / len(uploaded_imgs))

            st.success("🎉 ย่อรูปภาพเรียบร้อย!")

            if len(processed_files) == 1:
                f_name, f_bytes = processed_files[0]
                st.download_button(f"⬇️ ดาวน์โหลด {f_name}", f_bytes, file_name=f_name, mime="image/jpeg")
            else:
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                    for f_name, f_bytes in processed_files:
                        zf.writestr(f_name, f_bytes)
                zip_buffer.seek(0)
                st.download_button("⬇️ ดาวน์โหลดทั้งหมด (.ZIP)", zip_buffer, file_name="resized_images.zip", mime="application/zip")


# ==========================================
# จุดเริ่มต้นการทำงาน (Entry Point)
# ==========================================
if __name__ == "__main__":
    if check_password():
        main_app()
