import time
import json
import re
from playwright.sync_api import sync_playwright
import phonenumbers
from phonenumbers import carrier
from phonenumbers.phonenumberutil import number_type, PhoneNumberType

import mysql.connector
from mysql.connector import Error
conn = mysql.connector.connect(
    host='localhost',       # Ubah dengan host Anda (misal: 127.0.0.1)
    database='bpr',     # Ubah dengan nama database Anda
    user='root',            # Ubah dengan username MySQL Anda
    password=''  # Ubah dengan password MySQL Anda
)


def insert_data(nama,no_telp,alamat,website):

    grup = "garment"
    cursor = conn.cursor()
    insert_query = """
    INSERT INTO table_perusahaan_gmaps (nama, no_telp, alamat, website, grup) 
    VALUES (%s, %s, %s, %s, %s)
    """
    data_baru = (nama,no_telp,alamat,website,grup)
    cursor.execute(insert_query, data_baru)
    conn.commit()
    cursor.close()


with sync_playwright() as p:
    browser = p.chromium.launch(headless=False, args=["--start-maximized"])
    context = browser.new_context(no_viewport=True)
    page = context.new_page()


    #=====================================================================
    
    kata_kunci = "garment tekstil jawa tengah"
    kata_kunci_url = kata_kunci.replace(" ", "+")
    url_tujuan = f"https://google.com/maps/search/{kata_kunci_url}"
    
    #print(f"Mengakses URL: {url_tujuan}")
    page.goto(url_tujuan)
    
    # Tunggu feed kiri muncul
    page.wait_for_selector('div[role="feed"]', timeout=60000)
    time.sleep(3)
    panel_kiri = page.locator('div[role="feed"]')
    print("Mulai scrolling...")
    print()


    # for _ in range(1): 
    #     if panel_kiri.count() > 0:
    #         panel_kiri.evaluate("element => element.scrollBy(0, 1000)")
    #         time.sleep(4)


    #=======================================================
    tinggi_terakhir = 0
    percobaan_gagal = 0
    batas_maksimal_gagal = 3  # Berikan kesempatan mencoba 3 kali jika loading macet

    while True:
        # 1. Gulir panel kiri ke bawah
        panel_kiri.evaluate("element => element.scrollBy(0, 1200)")
        time.sleep(3.0)  # Ditambah menjadi 3 detik agar Google punya waktu loading data
        
        # 2. Hitung tinggi panel saat ini
        tinggi_sekarang = panel_kiri.evaluate("element => element.scrollHeight")
        
        # 3. Cek apakah teks akhir resmi dari Google sudah muncul
        teks_akhir_muncul = page.locator("text=Anda telah mencapai akhir daftar").count() > 0
        
        if teks_akhir_muncul:
            #print("[✓] Sukses! Konfirmasi resmi Google: Akhir daftar tercapai.")
            break
            
        # 4. LOGIKA TOLERANSI MACET: Jika tinggi tidak bertambah
        if tinggi_sekarang == tinggi_terakhir:
            percobaan_gagal += 1
            #print(f"   [!] Loading macet... Mencoba kembali ({percobaan_gagal}/{batas_maksimal_gagal})")
            
            # Jika sudah mencoba sebanyak batas maksimal dan tetap tidak bertambah, baru berhenti
            if percobaan_gagal >= batas_maksimal_gagal:
                #print("[✓] Scroll dihentikan setelah batas toleransi habis. Data maksimal didapatkan.")
                break
        else:
            # Jika tinggi bertambah sukses, reset hitungan gagal menjadi 0
            percobaan_gagal = 0
            tinggi_terakhir = tinggi_sekarang


            
    # Ambil element list tempat bisnis
    links = page.locator('a[href*="/maps/place/"]')
    jumlah_data = links.count()
    print(f"Ditemukan {jumlah_data} lokasi bisnis. Memulai ekstraksi...\n")
    
    daftar_perusahaan = []
    
    for i in range(jumlah_data):
        try:
            # 1. Lakukan klik agar panel kanan terbuka
            links.nth(i).click()
            time.sleep(3.5)  # Beri jeda agar panel kanan selesai me-render teks
            
            # --- SELEKTOR BARU (LEBIH DINAMIS & UNIVERSAL) ---
            
            # 2. Tangkap Nama Perusahaan
            # Kita ambil teks judul utama di panel kanan. Biasanya berupa tag H1 satu-satunya di area detail
            # elemen_nama = page.locator('div[role="main"] h1, h1').first
            # nama = elemen_nama.inner_text().strip() if elemen_nama.count() > 0 else "-"
            
            # # Jika nama gagal didapat, coba ambil dari teks link pembungkus di sebelah kiri
            # if nama == "-" or not nama:
            #     nama = links.nth(i).get_attribute("aria-label") or "-"

            nama = "-"
            
            # Percobaan 1: Menggunakan class spesifik teks judul Google Maps (Paling Akurat)
            if page.locator('h1.fontHeadlineLarge').count() > 0:
                nama = page.locator('h1.fontHeadlineLarge').first.inner_text().strip()
            
            # Percobaan 2: Mengambil H1 pertama yang ada di dalam panel detail kanan (role="main")
            elif page.locator('div[role="main"] h1').count() > 0:
                # Kita pastikan bukan mengambil judul halaman luar
                nama = page.locator('div[role="main"] h1').first.inner_text().strip()
            
            # Percobaan 3: Jika panel kanan lambat memuat, ambil nama dari atribut link daftar kiri
            if nama == "-" or not nama or "Hasil" in nama:
                # Mengambil teks penanda (aria-label) dari elemen yang diklik
                nama_mentah = links.nth(i).get_attribute("aria-label") or ""
                # Bersihkan teks jika mengandung kata tambahan dari Google
                nama = nama_mentah.replace("· Go to details", "").strip()


            if re.search(r'\b(pt|cv)\b', nama, re.IGNORECASE):
                # 3. Tangkap Alamat & Nomor Telepon Menggunakan Pola Struktur Ikon Google Maps
                # Google Maps meletakkan info detail di dalam button yang berderet di panel utama
                semua_tombol_detail = page.locator('div[role="main"] button')
                total_tombol = semua_tombol_detail.count()
                
                alamat = "-"
                telp = "-"
                website = "-"
                #page.pause()
                
                for k in range(total_tombol):
                    tombol = semua_tombol_detail.nth(k)
                    
                    teks_tombol = tombol.inner_text().strip()
                    data_item_id = tombol.get_attribute("data-item-id") or ""
                    href_link = tombol.get_attribute("href") or ""
                    
                    # Jika elemen kosong total, lewati
                    if not teks_tombol and not data_item_id and not href_link:
                        continue
                    
                    # --- A. DETEKSI ALAMAT ---
                    # Mencari kata kunci 'address' pada ID komponen Google Maps
                    if "address" in data_item_id:
                        alamat = teks_tombol
                    
                    # --- B. DETEKSI NOMOR TELEPON ---
                    # Mencari komponen yang mengandung ID awalan 'phone:tel:' bawaan Google
                    elif "phone:tel:" in data_item_id:
                        # Mengambil teks luar (Nomor telepon aslinya)
                        telp = teks_tombol
                    
                    # --- C. DETEKSI WEBSITE ---
                    # Mencari komponen yang mengandung ID 'authority' bawaan Google
                if website == "-":
                    locator_web_langsung = page.locator('div[role="main"] [aria-label^="Situs Web:"]').first
                    if locator_web_langsung.count() > 0:
                        href_langsung = locator_web_langsung.get_attribute("href") or ""
                        aria_label_langsung = locator_web_langsung.get_attribute("aria-label") or ""
                        if href_langsung and "google.com" not in href_langsung:
                            website = href_langsung
                        elif "situs web:" in aria_label_langsung.lower():
                            website = aria_label_langsung.split(":", 1)[-1].strip()


                # --- UJI COBA CETAK LOG SEMENTARA ---
                alamat_bersih = re.sub(r'[^\x00-\x7F]+', '', alamat).strip()
                telp_bersih = re.sub(r'[^\x00-\x7F]+', '', telp).strip()
                alamat_bersih = " ".join(alamat_bersih.split())
                telp_bersih = " ".join(telp_bersih.split())
                website_bersih = re.sub(r'[^\x00-\x7F]+', '', website).strip()
                website_bersih = " ".join(website_bersih.split())

                print(f"{i+1}")
                print(f"{nama}")
                print(f"{alamat_bersih}")
                print(f"{telp_bersih}")
                print(f"{website_bersih}")
                print()
                insert_data(nama,telp_bersih,alamat_bersih,website_bersih)
                time.sleep(5)

                # Masukkan data ke array tanpa filter ketat agar tidak zonk
                # data = {
                #     "nama": nama,
                #     "alamat": alamat_bersih,
                #     "nomor_hp": telp_bersih,
                #     "website" : website_bersih
                # }
                #daftar_perusahaan.append(data)
                #print(f"Sukses masuk array!\n")



            
        except Exception as e:
            print(f"   [x] Error pada item ke-{i+1}: {e}\n")
            continue
            
    #print("\n=== HASIL AKHIR SCRAPING GOOGLE MAPS ===")
    #print(json.dumps(daftar_perusahaan, indent=4))

    #====================================================================
    #====================================================================
    #====================================================================
    browser.close()
