# DL Repostium

Aplikasi web lokal untuk melihat informasi media dari URL lalu mengunduh video atau audio. Backend menggunakan FastAPI dan `yt-dlp`; FFmpeg diperlukan untuk mengubah audio menjadi MP3 dan membantu menggabungkan format video tertentu.

## Versi yang disarankan

| Komponen | Versi / paket |
| --- | --- |
| Python (Windows) | **3.13.x** — sesuai `runtime.txt` dan sudah digunakan untuk menjalankan proyek. |
| Python (Termux) | Gunakan paket `python` dari repositori Termux. Saat panduan ini diperbarui, repositori Termux menyediakan **Python 3.14.10**; versi paket dapat berubah mengikuti update Termux. |
| Dependensi Python | Gunakan versi yang dikunci di `requirements.txt` dengan `python -m pip install -r requirements.txt`. |
| FFmpeg | Versi yang tersedia melalui package manager sistem; harus dapat dipanggil sebagai `ffmpeg`. |
| Termux | Versi terbaru dari F-Droid atau GitHub resmi Termux. Hindari versi Play Store yang sudah tidak didukung. |

Dependensi utama yang saat ini dipatok adalah FastAPI 0.139.0, Pydantic 2.13.4, pydantic-core 2.46.4, Starlette 1.3.1, Uvicorn 0.50.0, dan yt-dlp 2026.7.4. Jangan memasang versi-versi ini satu per satu; `requirements.txt` juga mengunci dependensi pendukung agar versinya konsisten.

> **Catatan versi:** jangan gunakan perintah `pkg install python3.13` di Termux—Termux memasang Python dengan nama paket `python` dan tidak menyediakan pemilihan versi minor seperti itu. `runtime.txt` menyatakan Python 3.13 untuk lingkungan yang menghormati file tersebut, dan Python 3.13 sudah dicoba untuk proyek ini. Untuk Termux, gunakan versi yang disediakan repositori (saat ini 3.14.10). Versi `pydantic-core` yang dipatok menyatakan dukungan Python 3.14, tetapi pada Android mungkin harus dikompilasi dari source; karena itu perlu toolchain Rust dan C.

## Instalasi di Termux (Android)

Gunakan aplikasi Termux terbaru dari [F-Droid](https://f-droid.org/packages/com.termux/) atau [rilis resmi GitHub](https://github.com/termux/termux-app/releases). Buka Termux, lalu jalankan:

```bash
pkg update
pkg upgrade -y
pkg install -y git python ffmpeg clang rust
```

Periksa versi Python yang benar-benar terpasang dan pastikan FFmpeg tersedia:

```bash
python --version
ffmpeg -version
```

Jika hasil Python bukan 3.14.10 karena repositori sudah diperbarui, tidak perlu mencari paket bernama `python3.13`; lanjutkan dengan Python dari Termux. Versi dependensi tetap dipatok oleh `requirements.txt`.

Simpan proyek di direktori home Termux (bukan folder shared storage), lalu buat virtual environment dan pasang dependensi:

```bash
cd ~
git clone https://github.com/mfxnan/downloader.git
cd downloader
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Jika proyek sudah ada di perangkat, lewati `git clone` dan `cd downloader`, lalu masuk ke folder proyek yang bersangkutan.

### Jika instalasi `pydantic-core` gagal

`pydantic-core` memiliki komponen native Rust. Pada Android/Termux, pip biasanya perlu membangunnya dari source karena wheel yang tersedia mungkin tidak cocok dengan Android. Perintah instalasi Termux di atas sudah memasang `clang` dan `rust`; jika build tetap gagal, baca pesan error terakhir. Pastikan paket Termux sudah diperbarui dan coba ulang:

```bash
pkg update
pkg upgrade -y
pkg install -y clang rust
python -m pip install -r requirements.txt
```

Build native di Android dapat memerlukan waktu dan masih bisa gagal karena keterbatasan atau perubahan toolchain Termux. Jangan menghapus pin versi di `requirements.txt` sebagai langkah pertama.

### Menjalankan server

Dengan virtual environment masih aktif:

```bash
python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

Buka browser di perangkat Android yang sama dan kunjungi:

```text
http://127.0.0.1:8000
```

Biarkan Termux tetap berjalan selama aplikasi digunakan. Untuk menghentikan server, tekan **Ctrl+C** di Termux. Alamat `127.0.0.1` membatasi server ke perangkat lokal; jangan menggantinya dengan `0.0.0.0` kecuali memang ingin perangkat lain di jaringan mengakses server dan sudah memahami konsekuensi keamanannya.

## Instalasi lokal di Windows

Gunakan Python **3.13.x**, lalu dari folder proyek jalankan PowerShell:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Pasang FFmpeg dan pastikan `ffmpeg -version` dapat dijalankan dari terminal. Lalu mulai server:

```powershell
python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

Buka `http://127.0.0.1:8000`.

## Konfigurasi opsional

Aplikasi membaca konfigurasi berikut dari environment variables:

| Variabel | Default | Keterangan |
| --- | --- | --- |
| `HOST` | `127.0.0.1` | Host saat menjalankan `python app.py`. Untuk pemakaian lokal, pertahankan loopback. |
| `PORT` | `8000` | Port saat menjalankan `python app.py`. |
| `TEMP_DIR` | `tmp` di folder proyek | Lokasi file sementara hasil unduhan. |
| `MAX_CONCURRENT_DOWNLOADS` | `2` | Jumlah maksimum unduhan aktif. |
| `MAX_FILE_AGE_SECONDS` | `86400` | Umur file sementara sebelum dibersihkan. |
| `API_KEY` | tidak disetel | Jika disetel, request API memerlukan header key. Biasanya tidak dibutuhkan untuk penggunaan lokal pribadi. |
| `ALLOW_PRIVATE_URLS` | `false` | Mengizinkan URL menuju jaringan privat/lokal jika diaktifkan; biarkan nonaktif kecuali diperlukan. |

## Pemecahan masalah

- **`No module named ...`** — aktifkan virtual environment proyek lalu jalankan ulang `python -m pip install -r requirements.txt`.
- **Error build `pydantic-core`** — di Windows gunakan Python 3.13.x; di Termux gunakan `python` dari repositorinya serta pastikan `clang` dan `rust` terpasang.
- **Audio tidak menjadi MP3 atau video tidak tergabung dengan benar** — pastikan `ffmpeg -version` berhasil. Tutup dan jalankan ulang server setelah memasang FFmpeg.
- **Halaman tidak terbuka** — pastikan server masih berjalan dan buka alamat yang sama dengan port yang ditampilkan Uvicorn.
- **Unduhan gagal dari situs tertentu** — dukungan tergantung extractor `yt-dlp`, perubahan situs, akses jaringan, dan kebutuhan autentikasi situs tersebut.
