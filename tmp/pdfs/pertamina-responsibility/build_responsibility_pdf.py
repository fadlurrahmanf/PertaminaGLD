from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, Table, TableStyle,
    PageBreak, KeepTogether
)
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics

OUT = Path(r"D:\Github\PertaminaGLD\output\pdf\PertaminaGLD-Pembagian-Tugas-LGU-Pertamina.pdf")
OUT.parent.mkdir(parents=True, exist_ok=True)
PAGE = landscape(A4)
PW, PH = PAGE

INK = colors.HexColor("#111827")
MUTED = colors.HexColor("#5F6670")
BLUE = colors.HexColor("#246BFD")
PALE = colors.HexColor("#DDEEFF")
PANEL = colors.HexColor("#F1F3F5")
RULE = colors.HexColor("#C4C9D0")
AMBER = colors.HexColor("#F7B731")
GREEN = colors.HexColor("#268A5E")
WHITE = colors.white

font_regular = "Helvetica"
font_bold = "Helvetica-Bold"
arial = Path(r"C:\Windows\Fonts\arial.ttf")
arial_bold = Path(r"C:\Windows\Fonts\arialbd.ttf")
if arial.exists() and arial_bold.exists():
    pdfmetrics.registerFont(TTFont("ArialCustom", str(arial)))
    pdfmetrics.registerFont(TTFont("ArialCustom-Bold", str(arial_bold)))
    font_regular, font_bold = "ArialCustom", "ArialCustom-Bold"

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="CoverEyebrow", fontName=font_bold, fontSize=12, leading=15, textColor=MUTED, spaceAfter=28))
styles.add(ParagraphStyle(name="CoverTitle", fontName=font_bold, fontSize=31, leading=35, textColor=INK, spaceAfter=14))
styles.add(ParagraphStyle(name="CoverSub", fontName=font_regular, fontSize=14, leading=19, textColor=MUTED))
styles.add(ParagraphStyle(name="PageTitle", fontName=font_bold, fontSize=22, leading=26, textColor=INK, spaceAfter=8))
styles.add(ParagraphStyle(name="PageLead", fontName=font_regular, fontSize=11.5, leading=16, textColor=MUTED, spaceAfter=10))
styles.add(ParagraphStyle(name="Section", fontName=font_bold, fontSize=13, leading=16, textColor=BLUE, spaceAfter=6))
styles.add(ParagraphStyle(name="Body", fontName=font_regular, fontSize=10.2, leading=14, textColor=INK))
styles.add(ParagraphStyle(name="BodyBold", fontName=font_bold, fontSize=10.2, leading=14, textColor=INK))
styles.add(ParagraphStyle(name="Small", fontName=font_regular, fontSize=8.4, leading=11, textColor=MUTED))
styles.add(ParagraphStyle(name="Table", fontName=font_regular, fontSize=8.3, leading=11, textColor=INK))
styles.add(ParagraphStyle(name="TableBold", fontName=font_bold, fontSize=8.3, leading=11, textColor=INK))
styles.add(ParagraphStyle(name="Callout", fontName=font_bold, fontSize=10.3, leading=14, textColor=INK))

def p(text, style="Body"):
    return Paragraph(text, styles[style])

def bullet_table(items, width, accent=BLUE):
    rows=[]
    for item in items:
        rows.append([Paragraph("■", ParagraphStyle("sq", parent=styles["Body"], textColor=accent, fontSize=7, leading=13)), p(item)])
    t=Table(rows, colWidths=[6*mm, width-6*mm], hAlign="LEFT")
    t.setStyle(TableStyle([
        ("VALIGN",(0,0),(-1,-1),"TOP"),
        ("LEFTPADDING",(0,0),(-1,-1),0), ("RIGHTPADDING",(0,0),(-1,-1),2),
        ("TOPPADDING",(0,0),(-1,-1),2.5), ("BOTTOMPADDING",(0,0),(-1,-1),3.5),
    ]))
    return t

def info_box(title, body, width, fill=PANEL):
    t=Table([[p(title,"Section")],[p(body)]], colWidths=[width])
    t.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,-1),fill), ("BOX",(0,0),(-1,-1),0.7,RULE),
        ("LEFTPADDING",(0,0),(-1,-1),7*mm), ("RIGHTPADDING",(0,0),(-1,-1),7*mm),
        ("TOPPADDING",(0,0),(-1,0),5*mm), ("BOTTOMPADDING",(0,0),(-1,0),1*mm),
        ("TOPPADDING",(0,1),(-1,1),1*mm), ("BOTTOMPADDING",(0,1),(-1,1),5*mm),
    ]))
    return t

def header_footer(canvas, doc):
    canvas.saveState()
    page = canvas.getPageNumber()
    if page > 1:
        canvas.setStrokeColor(RULE); canvas.setLineWidth(0.5)
        canvas.line(18*mm, PH-14*mm, PW-18*mm, PH-14*mm)
        canvas.setFont(font_bold, 8); canvas.setFillColor(MUTED)
        canvas.drawString(18*mm, PH-10.5*mm, "PERTAMINA GLD - PEMBAGIAN TUGAS LGU & PERTAMINA")
        canvas.setFont(font_regular, 8)
        canvas.drawRightString(PW-18*mm, 9*mm, f"{page:02d}")
        canvas.drawString(18*mm, 9*mm, "Dokumen koordinasi - 13 Agustus 2026")
    canvas.restoreState()

frame = Frame(18*mm, 15*mm, PW-36*mm, PH-32*mm, leftPadding=0, rightPadding=0, topPadding=5*mm, bottomPadding=3*mm)
doc = BaseDocTemplate(str(OUT), pagesize=PAGE, title="Pembagian Tugas LGU dan Pertamina", author="LGU", subject="Kebutuhan GLD, CH, Gateway dan Server")
doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=header_footer)])
story=[]

# Cover
story += [Spacer(1,34*mm), p("PERTAMINA × LGU","CoverEyebrow"), p("Kebutuhan Lapangan dan<br/>Pembagian Tugas Integrasi","CoverTitle"), p("GLD · CH · Gateway · Server","CoverTitle"), Spacer(1,8*mm), p("Dokumen koordinasi untuk memastikan kebutuhan daya, instalasi, jaringan, server, dan tanggung jawab masing-masing pihak sebelum pemasangan lapangan.","CoverSub"), Spacer(1,22*mm)]
cover_callout=Table([[p("FOKUS DOKUMEN","Section"),p("Tugas LGU", "BodyBold"),p("Tugas Pertamina", "BodyBold"),p("Informasi yang harus ditutup", "BodyBold")]], colWidths=[42*mm,50*mm,58*mm,80*mm])
cover_callout.setStyle(TableStyle([("BACKGROUND",(0,0),(0,0),PALE),("BACKGROUND",(1,0),(-1,0),PANEL),("BOX",(0,0),(-1,-1),0.7,RULE),("INNERGRID",(0,0),(-1,-1),0.5,RULE),("VALIGN",(0,0),(-1,-1),"MIDDLE"),("LEFTPADDING",(0,0),(-1,-1),5*mm),("RIGHTPADDING",(0,0),(-1,-1),5*mm),("TOPPADDING",(0,0),(-1,-1),5*mm),("BOTTOMPADDING",(0,0),(-1,-1),5*mm)]))
story += [cover_callout, PageBreak()]

# GLD
story += [p("1. Kebutuhan dari sisi GLD","PageTitle"), p("GLD memerlukan suplai 24 VDC dengan kapasitas minimal 2 A yang tersedia secara kontinu untuk pengoperasian lapangan.","PageLead")]
left = [p("KEPUTUSAN / KONDISI SAAT INI","Section"), bullet_table([
    "Kebutuhan power GLD: <b>24 VDC dengan kapasitas minimal 2 A yang tersedia secara kontinu</b>; konfigurasi ini sudah ditetapkan untuk aplikasi lapangan.",
    "Rencana pemasangan GLD berada di dekat sensor existing agar dapat memanfaatkan sumber daya yang sudah tersedia.",
    "Pengembangan GLD berbasis baterai telah dianalisis, tetapi <b>belum memungkinkan untuk operasi kontinu</b> saat ini.",
    "Optimasi power management untuk sumber baterai masih berada dalam tahap pengembangan."
],112*mm)]
right = [p("KONFIRMASI YANG DIBUTUHKAN DARI PERTAMINA","Section"), bullet_table([
    "Memastikan sumber 24 VDC di dekat sensor existing benar-benar memiliki kapasitas yang cukup untuk menjalankan GLD.",
    "Memberikan informasi titik terminal, polaritas, kapasitas aktual, proteksi listrik, grounding, dan standar konektor/kabel di lapangan.",
    "Mendukung pengukuran dan verifikasi tegangan/arus pada titik pemasangan sebelum instalasi permanen.",
    "Memberikan ketentuan site apabila opsi baterai akan diuji atau diterapkan pada tahap pengembangan berikutnya."
],112*mm, GREEN)]
t=Table([[left,right]], colWidths=[120*mm,120*mm])
t.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"),("BACKGROUND",(0,0),(0,0),PANEL),("BACKGROUND",(1,0),(1,0),PALE),("BOX",(0,0),(-1,-1),0.7,RULE),("INNERGRID",(0,0),(-1,-1),0.5,RULE),("LEFTPADDING",(0,0),(-1,-1),6*mm),("RIGHTPADDING",(0,0),(-1,-1),6*mm),("TOPPADDING",(0,0),(-1,-1),6*mm),("BOTTOMPADDING",(0,0),(-1,-1),6*mm)]))
story += [t, Spacer(1,7*mm), info_box("BATAS PENERAPAN", "Untuk tahap lapangan saat ini, GLD menggunakan power 24 VDC. Opsi baterai tidak diposisikan sebagai sumber kontinu sampai optimasi power management selesai dan hasil pengembangannya divalidasi.", 240*mm, colors.HexColor("#FFF4D7")), PageBreak()]

# CH
story += [p("2. Kebutuhan dari sisi CH","PageTitle"), p("Mounting CH dan panel surya akan dirancang LGU agar sesuai dengan struktur tiang atau handrail existing di area Pertamina.","PageLead")]
ch_items=[
    ("Desain mounting", "LGU membuat mounting CH dan panel surya berdasarkan dimensi serta kondisi struktur existing Pertamina."),
    ("Panel surya", "Panel surya yang dipilih harus memiliki sertifikasi yang dapat diterima untuk penggunaan di area Pertamina."),
    ("Pelaksanaan instalasi", "Seluruh instalasi fisik di area Pertamina dilakukan oleh tim Pertamina menggunakan personel dan tools yang sesuai."),
    ("Mur, baut, dan kunci", "Pertamina memberikan ukuran mur/baut dan ukuran kunci pas yang lazim digunakan agar mounting LGU dapat disesuaikan."),
    ("Batas pemasangan", "Pertamina memberikan batas ketinggian antenna, area/titik berbahaya, larangan penetrasi, dan jalur pemasangan yang diperbolehkan."),
    ("Kabel panel surya - CH", "Pertamina memberikan jenis, spesifikasi, proteksi, dan standar instalasi kabel yang wajib digunakan."),
    ("Ketentuan baterai", "Pertamina menjelaskan ketentuan penggunaan baterai: jenis yang diizinkan, enclosure, proteksi, sertifikasi, inspeksi, dan pembatasan lokasi.")
]
rows=[]
for i,(topic,desc) in enumerate(ch_items,1):
    rows.append([p(f"{i:02d}","TableBold"),p(topic,"TableBold"),p(desc,"Table")])
cht=Table(rows,colWidths=[13*mm,48*mm,179*mm],repeatRows=0)
cht.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"),("BACKGROUND",(0,0),(0,-1),PALE),("ROWBACKGROUNDS",(1,0),(-1,-1),[WHITE,PANEL]),("BOX",(0,0),(-1,-1),0.7,RULE),("INNERGRID",(0,0),(-1,-1),0.4,RULE),("LEFTPADDING",(0,0),(-1,-1),4*mm),("RIGHTPADDING",(0,0),(-1,-1),4*mm),("TOPPADDING",(0,0),(-1,-1),3.2*mm),("BOTTOMPADDING",(0,0),(-1,-1),3.2*mm)]))
story += [cht, Spacer(1,6*mm), info_box("INPUT MINIMUM UNTUK FINALISASI MOUNTING", "Foto dan ukuran struktur existing, ukuran fastener, batas dimensi, batas tinggi antenna, rute kabel, klasifikasi area, serta daftar sertifikasi yang diterima Pertamina.",240*mm,PALE), PageBreak()]

# GW
story += [p("3. Kebutuhan dari sisi Gateway","PageTitle"), p("Gateway menghubungkan jaringan LoRa ke broker MQTT pada server melalui jaringan yang disediakan atau disetujui Pertamina.","PageLead")]
gw_left=[
    "Gateway terhubung ke broker MQTT menggunakan alamat IP atau hostname server/broker.",
    "Gateway menggunakan adaptor <b>5 VDC</b> dan node ditempatkan di dalam ruangan.",
    "Antenna Gateway direncanakan berada di rooftop; dibutuhkan akses, jalur kabel, grounding, dan ketentuan proteksi.",
    "Konfigurasi Wi-Fi saat ini menggunakan <b>SSID dan password</b>."
]
gw_right=[
    "Pertamina menjelaskan langkah registrasi jaringan agar Gateway dan server memiliki konektivitas IP yang diperlukan.",
    "Pertamina memberikan IP/FQDN broker, port, VLAN/subnet, DHCP/static IP, DNS, NTP, dan aturan firewall.",
    "Jika ada security tambahan selain SSID/password - misalnya MAC allowlist, 802.1X, certificate, TLS/mTLS, VPN, NAC, atau topic ACL - detail harus diberikan agar LGU dapat menyesuaikan sistem.",
    "Pertamina memastikan titik daya indoor, akses rooftop, batas antenna, rute coax, dan lightning protection."
]
gt=Table([[ [p("KONFIGURASI / RENCANA LGU","Section"),bullet_table(gw_left,110*mm)], [p("INFORMASI DARI PERTAMINA","Section"),bullet_table(gw_right,110*mm,GREEN)] ]], colWidths=[120*mm,120*mm])
gt.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"),("BACKGROUND",(0,0),(0,0),PANEL),("BACKGROUND",(1,0),(1,0),PALE),("BOX",(0,0),(-1,-1),0.7,RULE),("INNERGRID",(0,0),(-1,-1),0.5,RULE),("LEFTPADDING",(0,0),(-1,-1),6*mm),("RIGHTPADDING",(0,0),(-1,-1),6*mm),("TOPPADDING",(0,0),(-1,-1),6*mm),("BOTTOMPADDING",(0,0),(-1,-1),6*mm)]))
story += [gt, Spacer(1,5*mm)]
payload=Table([[p("< 1 KB","PageTitle"),p("90 byte / 10 detik","PageTitle"),p("VALIDASI MQTT","Section")],[p("Target kapasitas data Gateway ke server.","Small"),p("Nilai yang disampaikan untuk periode tercepat.","Small"),p("Ukuran paket MQTT aktual dapat bertambah karena JSON, topic, header TCP/IP, dan security. Ukur melalui packet capture saat SAT.","Small")]],colWidths=[55*mm,65*mm,120*mm])
payload.setStyle(TableStyle([("BACKGROUND",(0,0),(0,-1),PANEL),("BACKGROUND",(1,0),(1,-1),PALE),("BACKGROUND",(2,0),(2,-1),colors.HexColor("#FFF4D7")),("BOX",(0,0),(-1,-1),0.7,RULE),("INNERGRID",(0,0),(-1,-1),0.5,RULE),("VALIGN",(0,0),(-1,-1),"TOP"),("LEFTPADDING",(0,0),(-1,-1),5*mm),("RIGHTPADDING",(0,0),(-1,-1),5*mm),("TOPPADDING",(0,0),(-1,-1),4*mm),("BOTTOMPADDING",(0,0),(-1,-1),4*mm)]))
story += [payload, PageBreak()]

# Server
story += [p("4. Kebutuhan dari sisi Server","PageTitle"), p("LGU menyiapkan web dashboard beserta panduan instalasinya. Pertamina menyediakan informasi dan platform server tempat sistem akan dijalankan.","PageLead")]
server_table=Table([
    [p("DISEDIAKAN LGU","Section"),p("DIBUTUHKAN DARI PERTAMINA","Section")],
    [bullet_table(["Web dashboard untuk monitoring sistem.","Paket/panduan instalasi dan konfigurasi aplikasi.","Kebutuhan minimum CPU/RAM/storage, OS/runtime dan database yang didukung.","Daftar dependency, port, service, database schema, serta prosedur startup/backup aplikasi.","Dukungan instalasi, commissioning, pengujian, dan serah terima."],112*mm), bullet_table(["Spesifikasi komputer/server aktual: CPU, RAM, storage, availability, dan lokasi/VM.","OS dan versinya, hak administrator, kebijakan software/container, antivirus, dan patching.","Database standar yang digunakan/diizinkan serta retention, backup, restore, dan ownership DBA.","IP/FQDN, DNS, NTP, HTTPS/certificate, broker MQTT, firewall, account, dan security policy.","PIC server/network dan jadwal instalasi atau maintenance window."],112*mm,GREEN)]
],colWidths=[120*mm,120*mm])
server_table.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"),("BACKGROUND",(0,0),(0,-1),PANEL),("BACKGROUND",(1,0),(1,-1),PALE),("BOX",(0,0),(-1,-1),0.7,RULE),("INNERGRID",(0,0),(-1,-1),0.5,RULE),("LEFTPADDING",(0,0),(-1,-1),6*mm),("RIGHTPADDING",(0,0),(-1,-1),6*mm),("TOPPADDING",(0,0),(-1,-1),5*mm),("BOTTOMPADDING",(0,0),(-1,-1),5*mm)]))
story += [server_table, Spacer(1,8*mm), info_box("OUTPUT YANG DIHARAPKAN", "Server readiness sheet berisi spesifikasi host, OS, database, akses administrator, alamat broker, port/firewall, metode autentikasi, jadwal instalasi, PIC, serta kriteria acceptance.",240*mm,colors.HexColor("#E7F7EF")), PageBreak()]

responsibilities=[
    ("01 · Power GLD", "Menetapkan kebutuhan suplai 24 VDC dengan kapasitas minimal 2 A yang tersedia secara kontinu dan menyediakan detail koneksi perangkat.", "Menyediakan titik 24 VDC dan membuktikan kapasitasnya cukup melalui verifikasi tegangan/arus di lokasi."),
    ("02 · Lokasi GLD", "Mengusulkan pemasangan dekat sensor existing dan menyiapkan metode pemasangan.", "Memberikan akses, izin, titik pemasangan, serta informasi proteksi listrik dan area berbahaya."),
    ("03 · Battery GLD", "Melanjutkan pengembangan dan optimasi power management; tidak mengajukan operasi kontinu saat ini.", "Memberikan ketentuan site untuk pengujian atau penerapan baterai pada fase berikutnya."),
    ("04 · Mounting CH", "Mendesain dan membuat mounting sesuai struktur tiang/handrail existing.", "Memberikan foto, dimensi, beban/larangan, dan persetujuan desain terhadap struktur existing."),
    ("05 · Solar panel", "Memilih panel surya tersertifikasi dan menyerahkan dokumen sertifikasinya.", "Menetapkan jenis sertifikasi yang diterima dan menyetujui panel untuk area pemasangan."),
    ("06 · Instalasi CH", "Memberikan drawing, metode kerja, wiring, dan instruksi instalasi.", "Melaksanakan instalasi lapangan dengan personel, tools, akses, dan prosedur keselamatan Pertamina."),
    ("07 · Fastener", "Menyesuaikan mounting terhadap ukuran mur, baut, dan kunci yang disepakati.", "Memberikan ukuran mur/baut/kunci pas dan standar fastener yang digunakan di lapangan."),
    ("08 · Batas CH", "Menyesuaikan desain antenna, enclosure, dan kabel terhadap persyaratan site.", "Memberikan batas tinggi antenna, titik berbahaya, rute, grounding, serta standar kabel panel surya-CH."),
    ("09 · Battery CH", "Menyerahkan spesifikasi baterai, enclosure, proteksi, SDS, dan dokumen keselamatan.", "Menjelaskan dan menyetujui ketentuan penggunaan baterai di area Pertamina."),
    ("10 · Gateway fisik", "Menyediakan Gateway, adaptor 5 V, kebutuhan indoor, antenna dan detail kabel.", "Menyediakan titik daya/ruang indoor, akses rooftop, rute coax, grounding dan lightning protection."),
    ("11 · Registrasi jaringan", "Memberikan MAC/device list dan menyesuaikan konfigurasi Gateway sesuai parameter resmi.", "Memberikan prosedur registrasi, SSID/security, IP/DNS/NTP, VLAN, firewall, broker dan credential/certificate."),
    ("12 · MQTT & payload", "Menyediakan topic/payload spec dan menjalankan uji kirim 90 byte/10 detik serta packet capture.", "Menyediakan broker/ACL dan menyetujui limit payload/rate; mendukung verifikasi paket aktual saat SAT."),
    ("13 · Server/dashboard", "Menyediakan dashboard, installer, kebutuhan minimum sistem, dependency, database schema, dokumentasi dan training.", "Menyediakan spesifikasi aktual host/OS/database, akses admin, network, certificate, backup policy dan PIC operasi."),
    ("14 · Commissioning", "Menyiapkan FAT/SAT script, evidence form, troubleshooting guide dan handover package.", "Menjadwalkan instalasi/SAT, menghadirkan PIC terkait, menutup temuan dan menandatangani acceptance.")
]

def responsibility_page(title_text, data, first):
    story.append(p(title_text,"PageTitle"))
    story.append(p("Setiap baris harus memiliki PIC, target tanggal, dan bukti penyelesaian sebelum pemasangan dijadwalkan.","PageLead"))
    rows=[[p("LGU","TableBold"),p("PERTAMINA","TableBold")]]
    for topic,lgu,ptm in data:
        rows.append([p(f"<b>{topic}</b><br/>{lgu}","Table"),p(f"<b>{topic}</b><br/>{ptm}","Table")])
    tab=Table(rows,colWidths=[120*mm,120*mm],repeatRows=1)
    tab.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(0,0),BLUE),("BACKGROUND",(1,0),(1,0),GREEN),("TEXTCOLOR",(0,0),(-1,0),WHITE),
        ("ROWBACKGROUNDS",(0,1),(-1,-1),[WHITE,PANEL]),("BOX",(0,0),(-1,-1),0.8,RULE),("INNERGRID",(0,0),(-1,-1),0.45,RULE),
        ("VALIGN",(0,0),(-1,-1),"TOP"),("LEFTPADDING",(0,0),(-1,-1),4.5*mm),("RIGHTPADDING",(0,0),(-1,-1),4.5*mm),
        ("TOPPADDING",(0,0),(-1,-1),3.2*mm),("BOTTOMPADDING",(0,0),(-1,-1),3.2*mm),
    ]))
    story.append(tab)

responsibility_page("5. Tabel Pembagian Tugas - Bagian 1", responsibilities[:7], True)
story.append(PageBreak())
responsibility_page("5. Tabel Pembagian Tugas - Bagian 2", responsibilities[7:], False)
story.append(PageBreak())

# Closing / checklist
story += [p("6. Informasi yang Diminta dari Pertamina","PageTitle"), p("Daftar berikut menjadi input minimum agar desain akhir, instalasi, dan commissioning dapat diselesaikan tanpa asumsi lapangan.","PageLead")]
checklist=[
    "Bukti kesiapan titik power GLD 24 VDC 2 A: lokasi, polaritas, proteksi, grounding, dan hasil ukur.",
    "Data struktur mounting CH: foto, ukuran tiang/handrail, ukuran mur/baut/kunci, batas beban, dan area berbahaya.",
    "Standar solar panel, kabel panel-CH, baterai, enclosure, grounding, surge/lightning, dan sertifikasi.",
    "Lokasi Gateway indoor, titik adaptor 5 V, akses rooftop, batas antenna, jalur coax, dan proteksi petir.",
    "Prosedur registrasi jaringan: MAC, SSID/security, VLAN, DHCP/static IP, DNS, NTP, firewall, broker, port, ACL dan certificate.",
    "Spesifikasi server: VM/bare-metal, CPU/RAM/storage, OS, database, akses admin, backup, HTTPS, monitoring, dan PIC.",
    "Jadwal instalasi, daftar PIC, SAT scenario, kriteria lulus, mekanisme penutupan temuan, dan penandatangan acceptance."
]
ct=bullet_table(checklist,240*mm,GREEN)
story += [ct, Spacer(1,7*mm), info_box("CATATAN TEKNIS", "Istilah 'satu jaringan' pada Gateway berarti tersedia konektivitas IP/routing dari Gateway ke broker/server sesuai aturan firewall Pertamina; tidak selalu harus berada pada SSID atau subnet yang identik. Nilai 90 byte adalah target data yang disampaikan, sedangkan ukuran paket MQTT aktual perlu divalidasi karena terdapat overhead protokol dan security.",240*mm,colors.HexColor("#FFF4D7")), Spacer(1,6*mm), p("Setelah seluruh informasi di atas tersedia, LGU dapat memfinalisasi desain mounting, konfigurasi jaringan, installer server, serta dokumen FAT/SAT untuk persetujuan bersama.","Callout")]

doc.build(story)
print(f"WROTE {OUT}")
