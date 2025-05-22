from flask import Flask, render_template, redirect, url_for, request, flash, send_file
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user
from tinydb import TinyDB, Query
from werkzeug.security import generate_password_hash, check_password_hash
import pandas as pd
import io
import joblib
from pathlib import Path
from difflib import get_close_matches

app = Flask(__name__)
app.secret_key = 'your_secret_key'

def slugify(text):
    """Convert text to a simple slug"""
    return text.lower().replace(' ', '-').replace('?', '').replace('(', '').replace(')', '')

app.jinja_env.filters['slugify'] = slugify

# Initialize TinyDB
db = TinyDB('db.json')
users_db = db.table('users')
respondents_db = db.table('respondents')

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# User class for Flask-Login
class User(UserMixin):
    def __init__(self, user_data):
        self.id = user_data['id']
        self.username = user_data['username']
        self.password_hash = user_data['password_hash']

# Your conversion dictionary (same as before)
conversion_dict = {
    "Berapa jarak rumah Anda dari sungai terdekat? (dalam km)": {
        "< 500 m": 1,
        "500 m – 1 km": 0.8,
        "1 – 3 km": 0.6,
        "3 – 5 km": 0.4,
        "Lebih dari 5 km": 0.2,
    },
    "Dari bahan apa rumah Anda dibuat? (misal: batu, bata, lumpur, kayu)": {
        "Bambu atau material tradisional lainnya": 1,
        "Kayu": 0.8,
        "Bata tanpa pleseter": 0.6,
        "Bata dengan plester": 0.4,
        "Beton/Cor": 0.2,
    },
    "Apakah rumah Anda semi-permanen atau permanen": {
        "Semi – permanen": 1,
        "Permanen": 0,
    },
    "Berapa usia bangunan rumah Anda? (dalam tahun)": {
        "Kurang dari 5 tahun": 0.2,
        "5 – 10 tahun": 0.4,
        "10 – 20 tahun": 0.6,
        "Lebih dari 20 tahun": 1,
    },
    "Berapa jumlah lantai pada bangunan rumah Anda": {
        "Lebih dari 2 lantai": 0.2,
        "2 lantai": 0.6,
        "1 lantai": 1,
    },
    "Apakah rumah Anda memiliki akses ke listrik?": {
        "Ya": 0,
        "Tidak": 1,
    },
    "Apakah rumah Anda memiliki akses ke sumber air minum yang aman?": {
        "Tidak": 1,
        "Ya": 0,
    },
    "Apakah rumah Anda memiliki fasilitas sanitasi yang memadai? (missal: toilet, system pembuangan sampah)": {
        "Tidak": 1,
        "Ya": 0,
    },
    "Apakah area tempat tinggal Anda pernah terkena banjir dalam 10 tahun terkahir?": {
        "Tidak pernah": 1,
        "Ya, 1 – 2 kali": 0.6,
        "Ya, lebih dari 2 kali": 0.2,
    },
     "Jika ya, seberapa sering area tersebut terkena banjir": {
        "Setiap tahun": 1,
        "Setiap 2 – 5 tahun": 0.6,
        "Kurang sering dari itu": 0.2,
    },
    "Apakah ada system peringatan dini banjir di area tempat tinggal Anda?": {
        "Tidak": 1,
        "Ya": 0,
    },
    "Apakah Anda memiliki rencana evakuasi jika terjadi banjir?": {
        "Tidak": 1,
        "Ya": 0,
    },
    "Berapa jumlah anggota keluarga yang tinggal di rumah Anda?": {
        "Lebih dari 6 orang": 1,
        "5 – 6 orang": 0.6,
        "3 – 4 orang": 0.4,
        "1 – 2 orang": 0.2,
    },
    "Apakah ada anggota keluarga yang berusia di bawah 5 tahun atau di atas 60 tahun?": {
        "Ya, lebih dari satu": 1,
        "Ya, satu": 0.6,
        "Tidak": 0.2,
    },
    "Apakah ada anggota keluarga yang membutuhkan perawatan khusus atau memiliki disabilitas?": {
        "Ya": 1,
        "Tidak": 0,
    },
    "Apa tingkat pendidikan tertinggi yang telah dicapai oleh kepala rumah tangga?": {
        "Pendidikan Dasar atau tidak sekolah": 1,
        "Pendidikan menengah (SMP/SMA)": 0.6,
        "Pendidikan tinggi (Diploma/Sarjana atau lebih)": 0.2,
    },
    "Apakah Anda atau anggota keluarga lainnya pernah menerima informasi atau pelatihan tentang cara bertindak selama dan setelah banjir?": {
        "Ya": 0,
        "Tidak": 1,
    },
    "Seberapa sering Anda berinteraksi dengan tetangga atau anggota komunitas lainnya?": {
        "Jarang atau tidak pernah": 1,
        "Kadang–kadang": 0.6,
        "Sering": 0.2,
    },
    "Apakah ada sistem atau inisiatif dukungan komunitas di tempat Anda untuk membantu korban banjir?": {
        "Tidak": 1,
        "Ya": 0,
    },
    "Apakah Anda merasa komunitas Anda bersatu dan saling mendukung dalam situasi darurat?": {
        "Tidak": 1,
        "Ya": 0,
    },
     "Apakah ada organisasi (pemerintah, LSM, atau lainnya) yang Anda kenal dan dapat dihubungi untuk mendapatkan bantuan dalam situasi banjir?": {
        "Tidak": 1,
        "Ya": 0,
    },
    "Bagaimana Anda biasanya mendapatkan informasi penting selama situasi darurat? (misalnya radio, TV, internet, media sosial)": {
        "Tidak mendapatkan informasi": 1,
        "Radio atau TV": 0.6,
        "Media sosial atau internet": 0.2,
    },
    "Apakah rumah Anda pernah terdampak banjir sebelumnya?": {
        "Tidak pernah": 1,
        "Ya, pernah terdampak banjir": 0,
    },
    "Bagaimana Anda menilai tingkat risiko banjir di area tempat tinggal Anda saat ini?": {
        "Tinggi": 1,
        "Sedang": 0.6,
        "Rendah": 0.2,
    },
    "Apakah Anda pernah mengambil langkah-langkah untuk mengurangi risiko banjir di rumah atau lingkungan Anda? Jika ya, langkah apa yang telah diambil?": {
        "Tidak pernah": 1,
        "Ya, telah mengambil Langkah–langkah": 0.2,
    },
    "Menurut Anda, apa langkah paling efektif yang bisa dilakukan untuk mengurangi dampak banjir di komunitas Anda?": {
        "Lainnya": 1,
        "Pembangunan system peringatan dini dan evakuasi": 0.8,
        "Pendidikan masyarakat tentang pengelolaan risiko banjir": 0.6,
        "Penguatan tanggul dan infrastruktur penahan air": 0.4,
        "Peningkatan system drainase dan pengelolaan air": 0.2,
    },
    "Apa sumber penghasilan utama Anda? (Contoh: pertanian, perdagangan, pekerjaan formal, dll.)": {
        "Pertanian atau pekerjaan yang sangat tergantung pada cuaca": 1,
        "Pekerjaan informal atau harian": 0.8,
        "Pekerjaan formal di sektor swasta": 0.6,
        "Pensiunan atau tidak bekerja tetapi memiliki sumber penghasilan tetap":0.4,
        "Pekerjaan formal di sektor pemerintah": 0.2
    },
    "Apakah pekerjaan Anda tergantung pada kondisi cuaca? Jika ya, jelaskan bagaimana cuaca mempengaruhi pekerjaan Anda.": {
        "Sangat tergantung": 1,
        "Agak tergantung": 0.6,
        "Tidak tergantung": 0.2
    },
    "Berapa pendapatan rata-rata bulanan keluarga Anda?": {
        "Kurang dari Rp1.000.000": 1,
        "Rp1.000.000 – Rp3.000.000": 0.8,
        "Rp3.000.000 – Rp5.000.000": 0.6,
        "Lebih dari Rp5.000.000": 0.2
    },
    "Apakah Anda memiliki tabungan atau dana darurat yang dapat digunakan dalam situasi darurat seperti banjir?": {
        "Tidak": 1,
        "Ya, tetapi kurang dari Rp5.000.000": 0.6,
        "Ya, lebih dari Rp5.000.000": 0.2
    },
    "Apa saja jenis aset yang Anda miliki? (Contoh: tanah, rumah, kendaraan, peralatan bisnis, ternak, dll.)": {
        "Tidak memiliki aset signifikan": 1,
        "Memiliki aset non–likuid (tanah, rumah, dll.)": 0.6,
        "Memiliki aset likuid (tabungan, saham, dll.)": 0.2
    },
    "Apakah aset Anda pernah terdampak oleh banjir sebelumnya? Jika ya, sejauh mana kerusakan yang terjadi?": {
        "Ya, kerusakan signifikan": 1,
        "Ya, kerusakan minor": 0.6,
        "Tidak pernah terdampak": 0.2
    },
    "Berapa perkiraan kerugian finansial yang Anda alami akibat banjir terakhir?": {
        "Lebih dari Rp10.000.000": 1,
        "Rp5.000.000 – Rp10.000.000": 0.6,
        "Kurang dari Rp5.000.000": 0.2
    },
    "Seberapa lama waktu yang dibutuhkan untuk pulih dari dampak finansial banjir tersebut?": {
        "Lebih dari 1 tahun": 1,
        "6 bulan – 1 tahun": 0.6,
        "Kurang dari 6 bulan": 0.2
    },
    "Apakah Anda memiliki akses ke layanan keuangan seperti kredit atau pinjaman? Jika ya, apakah Anda pernah menggunakan layanan tersebut untuk pemulihan pasca banjir?": {
        "Tidak memiliki akses": 1,
        "Memiliki akses tetapi tidak pernah menggunakan": 0.6,
        "Memiliki akses dan pernah menggunakan": 0.2
    },
    # sus
    "Apakah ada program bantuan keuangan atau asuransi banjir yang tersedia untuk Anda? Jika ya, apakah Anda telah mendaftar atau menggunakan program tersebut?": {
        "Tidak ada program bantuan atau asuransi banjir": 1,
        "Ada program tetapi tidak mendaftar atau menggunakan": 0.6,
        "Ada program dan telah mendaftar atau menggunakan":0.4,
        "Memiliki akses dan pernah menggunakan": 0.2
    },
    "Apakah Anda pernah mengubah strategi ekonomi keluarga (misalnya diversifikasi sumber penghasilan, perubahan jenis usaha) sebagai respons terhadap risiko banjir?": {
        "Tidak pernah mengubah strategi ekonomi": 1,
        "Pernah mengubah strategi ekonomi": 0
    },
    "Bagaimana Anda biasanya mengatasi kerugian ekonomi yang disebabkan oleh banjir?": {
        "Tidak bisa mengatasi kerugian ekonomi": 1,
        "Menggunakan kredit atau pinjaman": 0.8,
        "Menerima bantuan pemerintah atau LSM": 0.6,
        "Menggunakan bantuan dari keluarga atau teman": 0.4,
        "Menggunakan tabungan atau cadangan keuangan": 0.2
    },
    "Apakah area tempat tinggal Anda berada dalam atau dekat dengan area yang sering tergenang banjir?": {
        "Sering": 1,
        "Kadang–kadang": 0.6,
        "Tidak pernah": 0.2
    },
    "Seberapa sering Anda melihat penumpukan sampah di saluran air atau sungai di dekat tempat tinggal Anda?": {
        "Sering": 1,
        "Kadang–kadang": 0.6,
        "Tidak pernah": 0.2
    },
    # sus
    "Apakah di sekitar tempat tinggal Anda terdapat area hijau, seperti taman atau hutan?": {
        "Tidak ada":1,
        "Sedikit": 0.6,
        "Ya, banyak": 0.2
    },
    "Apakah Anda atau komunitas Anda terlibat dalam kegiatan penanaman pohon atau rehabilitasi lahan?": {
        "Tidak pernah": 1,
        "Sesekali": 0.6,
        "Ya, secara aktif": 0.2
    },
    "Bagaimana kondisi sistem drainase di area tempat tinggal Anda? (Baik, cukup, buruk)": {
        "Buruk, sering terjadi penyumbatan": 1,
        "Cukup, tapi ada beberapa masalah": 0.6,
        "Baik, tidak ada masalah": 0.2
    },
    "Apakah Anda mengambil langkah-langkah untuk mengurangi risiko banjir, seperti membuat sumur resapan atau sistem penampungan air hujan?": {
        "Tidak": 1,
        "Rencana untuk melakukannya": 0.6,
        "Ya, ada beberapa langkah yang telah diambil": 0.2
    },
    "Seberapa sering Anda atau komunitas Anda melakukan kegiatan bersih-bersih lingkungan?": {
        "Tidak pernah": 1,
        "Sesekali": 0.6,
        "Rutin": 0.2
    },
    "Apakah Anda menggunakan atau mendorong penggunaan bahan yang ramah lingkungan dalam kehidupan sehari-hari?": {
        "Tidak pernah": 1,
        "Kadang–kadang": 0.6,
        "Selalu": 0.2
    },
    "Apa dampak lingkungan yang Anda amati atau alami setelah banjir terjadi? (Misalnya: erosi tanah, kerusakan habitat, polusi air)": {
        "Dampak serius, seperti erosi dan polusi": 1,
        "Dampak ringan pada tanah dan air": 0.6,
        "Tidak ada dampak signifikan": 0.2
    },
    "Bagaimana perubahan kondisi lingkungan setelah banjir mempengaruhi komunitas atau kehidupan sehari-hari Anda?": {
        "Pengaruh serius, kehidupan terganggu dalam waktu lama": 1,
        "Pengaruh ringan, kehidupan kembali normal dalam beberapa hari": 0.6,
        "Tidak ada pengaruh": 0.2
    },
    "Seberapa sadar Anda tentang pengaruh praktik lingkungan terhadap risiko banjir?": {
        "Tidak sadar sama sekali": 1,
        "Kurang sadar": 0.8,
        "Cukup sadar": 0.6,
        "Sadar": 0.4,
        "Sangat sadar": 0.2
    },
    "Apakah Anda berpartisipasi dalam program atau inisiatif pemerintah atau LSM yang berfokus pada pengelolaan lingkungan dan pencegahan banjir?": {
        "Tidak pernah berpartisipasi": 1,
        "Jarang berpartisipasi": 0.8,
        "Kadang–kadang berpartisipasi": 0.6,
        "Sering berpartisipasi": 0.4,
        "Selalu berpartisipasi": 0.2
    },
    "Seberapa sering pemerintah atau organisasi lain memberikan informasi atau pelatihan tentang pengelolaan risiko banjir kepada komunitas Anda?": {
        "Tidak pernah": 1,
        "Kadang–kadang": 0.6,
        "Sering": 0.2
    },
    "Apakah informasi tentang pengelolaan dan mitigasi risiko banjir mudah diakses oleh masyarakat luas di area Anda?": {
        "Tidak, sangat sulit ditemukan": 1,
        "Ada, tapi tidak selalu mudah diakses": 0.6,
        "Ya, sangat mudah diakses": 0.2
    },
    # darisini
    "Bagaimana Anda menilai kualitas infrastruktur penanggulangan banjir (seperti bendungan, tanggul, dan sistem drainase) di area Anda?": {
        "Buruk dan tidak efektif": 1,
        "Cukup baik tetapi perlu perbaikan": 0.6,
        "Sangat baik dan efektif": 0.2
    },
    "Seberapa efektif layanan respons darurat (seperti tim penyelamat dan pemadam kebakaran) saat terjadi banjir?": {
        "Tidak efektif dan sering terlambat": 1,
        "Cukup responsif tetapi perlu peningkatan": 0.6,
        "Sangat efektif dan responsif": 0.2
    },
    "Apakah Anda mengetahui adanya kebijakan atau regulasi pemerintah terkait pengelolaan banjir di area Anda?": {
        "Tidak tahu atau tidak ada": 1,
        "Saya tahu ada, tetapi tidak terlalu memahaminya": 0.6,
        "Ya, dan saya memahaminya dengan baik": 0.2
    },
    "Apakah kebijakan dan regulasi tersebut diimplementasikan dengan baik dan memiliki dampak nyata dalam mengurangi risiko banjir?": {
        "Tidak berdampak atau tidak konsisten": 1,
        "Ada dampak, tetapi tidak signifikan": 0.6,
        "Ya, sangat berdampak": 0.2
    },
    "Seberapa sering pemerintah setempat melibatkan masyarakat dalam proses pengambilan keputusan terkait pengelolaan risiko banjir?": {
        "Jarang atau tidak pernah": 1,
        "Kadang–kadang, tapi kurang melibatkan": 0.6,
        "Sering dan secara transparan": 0.2
    },
    "Apakah ada mekanisme kolaborasi antara pemerintah, sektor swasta, dan masyarakat sipil dalam upaya pengurangan risiko banjir?": {
        "Tidak ada atau sangat jarang": 1,
        "Ada, tetapi tidak efektif": 0.6,
        "Ya, ada dan berfungsi dengan baik": 0.2
    },
    "Seberapa adil menurut Anda distribusi bantuan dan sumber daya untuk mitigasi dan pemulihan dari banjir?": {
        "Sangat tidak adil": 1,
        "Tidak adil": 0.8,
        "Cukup adil": 0.6,
        "Adil": 0.4,
        "Sangat adil": 0.2
    },
    "Apakah ada program bantuan khusus dari pemerintah atau organisasi lain untuk kelompok rentan atau daerah yang sangat terdampak?": {
        "Tidak ada program bantuan khusus": 1,
        "Ada program bantuan, tetapi kurang efektif": 0.6,
        "Ada program bantuan yang efektif": 0.2
    },
    "Bagaimana Anda menilai kapasitas lembaga-lembaga pemerintah atau organisasi lain dalam mengelola risiko dan dampak banjir?": {
        "Sangat rendah": 1,
        "Rendah": 0.8,
        "Sedang": 0.6,
        "Tinggi": 0.4,
        "Sangat tinggi": 0.2
    },
    "Apakah ada upaya untuk memastikan keberlanjutan program dan intervensi pengelolaan banjir?": {
        "Tidak ada upaya keberlanjutan": 1,
        "Ada upaya, tetapi tidak konsisten": 0.6,
        "Ada upaya yang konsisten": 0.2
    },
    "Seberapa besar Anda merasa terancam oleh potensi banjir di area tempat tinggal Anda?": {
        "Sangat merasa terancam":1,
        "Merasa terancam sekali": 0.8,
        "Cukup merasa terancam": 0.6,
        "Sedikit merasa terancam": 0.4,
        "Tidak merasa terancam": 0.2
    },
    "Bagaimana Anda menilai tingkat keparahan dampak banjir terhadap kehidupan dan properti Anda?": {
        "Sangat tinggi": 1,
        "Tinggi": 0.8,
        "Sedang": 0.6,
        "Rendah": 0.4,
        "Sangat rendah": 0.2
    },
    "Seberapa baik Anda memahami penyebab dan dampak banjir?": {
        "Tidak memahami sama sekali":1,
        "Kurang memahami": 0.8,
        "Cukup memahami": 0.6,
        "Sangat memahami": 0.2
    },
    "Apakah Anda mengetahui cara-cara efektif untuk mengurangi risiko dan dampak banjir pada diri Anda dan komunitas?": {
        "Tidak tahu sama sekali": 1,
        "Tahu beberapa cara": 0.6,
        "Tahu banyak cara": 0.2
    },
    "Seberapa penting menurut Anda untuk mengambil tindakan pencegahan terhadap banjir?": {
        "Tidak penting": 1,
        "Kurang penting": 0.6,
        "Sangat penting": 0.2
    },
    "Apakah Anda bersedia mengubah perilaku atau mengambil tindakan untuk mengurangi risiko banjir?": {
        "Tidak bersedia": 1,
        "Mungkin bersedia": 0.6,
        "Sangat bersedia": 0.2
    },
    "Apakah Anda memiliki rencana atau persiapan khusus untuk menghadapi banjir? (Misalnya: kit darurat, rencana evakuasi)": {
        "Tidak ada": 1,
        "Ada, tetapi tidak lengkap": 0.6,
        "Ada dan lengkap": 0.2
    },
    "Seberapa yakin Anda dengan kemampuan Anda dan komunitas untuk merespons secara efektif saat terjadi banjir?": {
        "Tidak yakin": 1,
        "Cukup yakin": 0.6,
        "Sangat yakin": 0.2
    },
    "Seberapa besar kepercayaan Anda terhadap informasi dan peringatan banjir yang diberikan oleh otoritas terkait?": {
        "Tidak percaya sama sekali": 1,
        "Kurang percaya": 0.6,
        "Cukup percaya": 0.4,
        "Sangat percaya": 0.2
    },
    "Apakah Anda merasa bahwa pemerintah dan lembaga terkait merespons dengan baik terhadap kejadian banjir sebelumnya?": {
        "Tidak sama sekali": 1,
        "Kurang responsif": 0.6,
        "Cukup responsif": 0.4,
        "Sangat responsif": 0.2
    },
    "Apakah banjir sebelumnya mempengaruhi sikap dan perilaku Anda terhadap risiko banjir?": {
        "Tidak berpengaruh": 1,
        "Sedikit berpengaruh": 0.6,
        "Cukup berpengaruh": 0.4,
        "Sangat berpengaruh": 0.2
    },
    "Apakah pengalaman tersebut membuat Anda lebih proaktif dalam mengambil tindakan pencegahan?": {
        "Tidak, sama sekali tidak lebih proaktif": 1,
        "Sedikit lebih proaktif": 0.6,
        "Cukup lebih proaktif": 0.4,
        "Sangat lebih proaktif": 0.2
    },
    
}

@login_manager.user_loader
def load_user(user_id):
    UserQuery = Query()
    user_data = users_db.get(UserQuery.id == int(user_id))
    if user_data:
        return User(user_data)
    return None

# Routes for register, login, logout
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        UserQuery = Query()
        if users_db.search(UserQuery.username == username):
            flash('Username already exists')
            return redirect(url_for('register'))
        
        user_id = len(users_db) + 1
        users_db.insert({
            'id': user_id,
            'username': username,
            'password_hash': generate_password_hash(password)
        })
        
        flash('User registered! Please login.')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        UserQuery = Query()
        user_data = users_db.get(UserQuery.username == username)
        
        if user_data and check_password_hash(user_data['password_hash'], password):
            user = User(user_data)
            login_user(user)
            return redirect(url_for('about'))
        else:
            flash('Invalid username or password', 'error')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# Dashboard
@app.route('/dashboard')
@login_required
def dashboard():
    respondents = respondents_db.all()
    return render_template('dashboard.html', respondents=respondents)

# Add respondent manually
@app.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    if request.method == 'POST':
        name = request.form['name']
        respondent_data = {'name': name}
        
        # Process each question from the form
        for question in conversion_dict:
            answer = request.form.get(question)
            if answer:
                # Convert answer to numerical value using conversion_dict
                numerical_value = conversion_dict[question].get(answer, 0)
                respondent_data[question] = numerical_value
        
        respondents_db.insert(respondent_data)
        flash('Respondent added')
        return redirect(url_for('dashboard'))
    
    return render_template('add.html', 
                         questions=conversion_dict.keys(),
                         conversion_dict=conversion_dict)

# Export respondents to xlsx
@app.route('/export')
@login_required
def export():
    respondents = respondents_db.all()
    
    # Prepare data with all questions
    data = []
    for r in respondents:
        respondent_data = {'Name': r.get('name', '')}
        
        # Add all question values
        for question in conversion_dict:
            respondent_data[question] = r.get(question, '')
        
        respondent_data['Result'] = r.get('result', '')
        respondent_data['Prob_Class_0'] = r.get('Prob_Class_0', '')
        respondent_data['Prob_Class_1'] = r.get('Prob_Class_1', '')
        respondent_data['Prob_Class_2'] = r.get('Prob_Class_2', '')
        data.append(respondent_data)
    
    df = pd.DataFrame(data)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Respondents')
    output.seek(0)
    return send_file(output, download_name="hasil_prediksi.xlsx", as_attachment=True)

# Import respondents from xlsx
@app.route('/import', methods=['GET', 'POST'])
@login_required
def import_data():
    if request.method == 'POST':
        file = request.files['file']
        if not file or file.filename == '':
            flash('No file uploaded', 'error')
            return redirect(url_for('import_data'))

        try:
            df = pd.read_excel(file)
            imported_count = 0
            fuzzy_matches = {}  
            
            # Check for required columns
            required_columns = ['Nama', 'Apakah Bapak Ibu bersedia melanjutkan pengisian kuesioner?']
            if not all(col in df.columns for col in required_columns):
                missing = [col for col in required_columns if col not in df.columns]
                flash(f'Missing required columns: {", ".join(missing)}', 'error')
                return redirect(url_for('import_data'))
            
            # Process each row
            for index, row in df.iterrows():
                # Skip if respondent didn't agree to continue
                consent = str(row.get('Apakah Bapak Ibu bersedia melanjutkan pengisian kuesioner?', '')).strip().lower()
                if 'tidak' in consent or consent != 'ya, saya bersedia':
                    continue
                
                name = str(row.get('Nama', '')).strip()
                if not name:
                    continue
                    
                respondent_data = {
                    'name': name,
                    'kecamatan': str(row.get('Kecamatan tempat tinggal', '')).strip(),
                    'consent': True
                }
                
                # Process survey questions
                for question in conversion_dict:
                    if question in row:
                        answer = row[question]
                        if pd.isna(answer):
                            respondent_data[question] = 0
                            continue
                            
                        # Handle different answer types
                        answer_str = str(answer).strip()
                        
                        # Exact match first
                        if answer_str in conversion_dict[question]:
                            numerical_value = conversion_dict[question][answer_str]
                        else:
                            # Fuzzy matching for similar answers
                            possible_answers = list(conversion_dict[question].keys())
                            matches = get_close_matches(answer_str, possible_answers, n=1, cutoff=0.6)
                            
                            if matches:
                                matched_answer = matches[0]
                                numerical_value = conversion_dict[question][matched_answer]
                                fuzzy_matches[f"{question}: {answer_str}"] = matched_answer
                            else:
                                numerical_value = 0  # Default if no match found
                        
                        respondent_data[question] = numerical_value
                
                # Insert into database
                respondents_db.insert(respondent_data)
                imported_count += 1
            
            # Show fuzzy match results to user
            if fuzzy_matches:
                match_messages = [f"'{orig}' → '{match}'" for orig, match in fuzzy_matches.items()]
                # flash(f"Used fuzzy matching for: {', '.join(match_messages)}", 'info')
            
            if imported_count > 0:
                flash(f'Successfully imported {imported_count} respondents', 'success')
            else:
                flash('No valid respondents found in the file', 'warning')
            return redirect(url_for('dashboard'))
            
        except Exception as e:
            flash(f'Error importing file: {str(e)}', 'error')
            return redirect(url_for('import_data'))
    
    return render_template('import.html')

# Load your ML model once 
try:
    model_path = Path(__file__).parent / 'model.pkl'
    model = joblib.load(model_path)
    print("Model loaded successfully. Model type:", type(model))
    print("Model classes:", model.named_steps['svm'].classes_)  
except Exception as e:
    print("Error loading model:", str(e))
    model = None

# Process respondents using ML model
@app.route('/process')
@login_required
def process():
    if model is None:
        flash('Model not loaded correctly', 'error')
        return redirect(url_for('dashboard'))

    respondents = respondents_db.all()
    if not respondents:
        flash('No respondents to process', 'warning')
        return redirect(url_for('dashboard'))

    try:
        # Prepare DataFrame with the same structure as training data
        data = []
        for r in respondents:
            row = {'name': r.get('name', '')}
            for question in conversion_dict.keys():
                row[question] = r.get(question, 0)
            data.append(row)
        
        df = pd.DataFrame(data)
        X_new = df.drop(columns=['name']) if 'name' in df.columns else df

        # Mapping dari angka ke label klasifikasi
        label_mapping = {
            0: 'LOW',
            1: 'MODERATE',
            2: 'HIGH'
        }

        # Get predictions and probabilities
        y_pred = model.predict(X_new)
        y_proba = model.predict_proba(X_new)

        # Counter untuk masing-masing label
        low_count = 0
        moderate_count = 0
        high_count = 0

        # Update respondents with full results
        for i, r in enumerate(respondents):
            label = label_mapping.get(y_pred[i], 'UNKNOWN')

            if label == 'LOW':
                low_count += 1
            elif label == 'MODERATE':
                moderate_count += 1
            elif label == 'HIGH':
                high_count += 1

            update_data = {
                'result': label,
                'Prob_Class_0': float(y_proba[i][0]),
                'Prob_Class_1': float(y_proba[i][1]),
                'Prob_Class_2': float(y_proba[i][2]),
                'probability': float(y_proba[i].max())
            }
            respondents_db.update(update_data, doc_ids=[r.doc_id])

        flash(f'Processed {len(respondents)} respondents: LOW={low_count}, MODERATE={moderate_count}, HIGH={high_count}', 'success')
    
    except Exception as e:
        flash(f'Processing failed: {str(e)}', 'error')
    
    return redirect(url_for('dashboard'))

@app.route('/respondent/<int:doc_id>/process', methods=['POST'])
@login_required
def process_respondent(doc_id):
    if model is None:
        flash('Model not loaded correctly', 'error')
        return redirect(url_for('dashboard'))

    respondent = respondents_db.get(doc_id=doc_id)
    if not respondent:
        flash('Respondent not found', 'error')
        return redirect(url_for('dashboard'))

    try:
        # Prepare data for single respondent
        data = {q: respondent.get(q, 0) for q in conversion_dict.keys()}
        df = pd.DataFrame([data])
        
        # Make prediction
        y_pred = model.predict(df)
        y_proba = model.predict_proba(df)
        
        # Update respondent
        respondents_db.update({
            'result': str(y_pred[0]),
            'Prob_Class_0': float(y_proba[0][0]),
            'Prob_Class_1': float(y_proba[0][1]),
            'Prob_Class_2': float(y_proba[0][2]),
            'probability': float(y_proba[0].max())
        }, doc_ids=[doc_id])
        
        flash('Respondent processed successfully', 'success')
    except Exception as e:
        flash(f'Processing failed: {str(e)}', 'error')
    
    return redirect(url_for('dashboard'))

@app.route('/respondent/<int:doc_id>')
@login_required
def view_respondent(doc_id):
    respondent = respondents_db.get(doc_id=doc_id)
    if not respondent:
        flash('Respondent not found', 'error')
        return redirect(url_for('dashboard'))
    
    # Organize data for display
    respondent_data = {
        'info': {
            'Name': respondent.get('name', ''),
            'Kecamatan': respondent.get('kecamatan', ''),
            'Result': respondent.get('result', 'Not processed'),
            'Confidence': f"{float(respondent.get('probability', 0)) * 100}%" if respondent.get('probability') else 'N/A'
        },
        'answers': [],
        'probabilities': {
            'Class 0': f"{float(respondent.get('Prob_Class_0', 0)) * 100}%",
            'Class 1': f"{float(respondent.get('Prob_Class_1', 0)) * 100}%",
            'Class 2': f"{float(respondent.get('Prob_Class_2', 0)) * 100}%"
        }
    }

    
    # Add all survey answers
    for question in conversion_dict:
        answer = respondent.get(question, '')
        original_options = conversion_dict[question]
        
        # Find the original text for the numerical value
        original_answer = None
        if answer != '':
            for opt_text, opt_value in original_options.items():
                if opt_value == answer:
                    original_answer = opt_text
                    break
        
        respondent_data['answers'].append({
            'question': question,
            'value': answer,
            'original_text': original_answer or str(answer)
        })
    
    return render_template('view_respondent.html', respondent=respondent_data)

@app.route('/respondent/<int:doc_id>/delete', methods=['POST'])
@login_required
def delete_respondent(doc_id):
    try:
        respondents_db.remove(doc_ids=[doc_id])
        flash('Respondent deleted successfully', 'success')
    except Exception as e:
        flash(f'Error deleting respondent: {str(e)}', 'error')
    return redirect(url_for('dashboard'))

@app.route('/respondents/delete_all', methods=['POST'])
@login_required
def delete_all_respondents():
    try:
        respondents_db.truncate()  # Menghapus semua data
        flash('All respondents have been deleted.', 'success')
    except Exception as e:
        flash(f'Failed to delete all respondents: {str(e)}', 'error')
    return redirect(url_for('dashboard'))


@app.route('/about')
def about():
    current_year = '2025'
    respondent_count = len(respondents_db)
    return render_template('about.html', 
                         current_year=current_year,
                         respondent_count=respondent_count)

@app.route('/test-model')
def test_model():
    # Create test input matching your training data
    test_data = {q: 0.5 for q in conversion_dict.keys()}
    test_df = pd.DataFrame([test_data])
    
    try:
        pred = model.predict(test_df)
        return f"Model test successful. Prediction: {pred[0]}"
    except Exception as e:
        return f"Model test failed: {str(e)}"

@app.route('/')
def index():
    return redirect(url_for('login'))

if __name__ == '__main__':
    # Create admin user if not exists
    UserQuery = Query()
    if not users_db.search(UserQuery.username == 'admin'):
        users_db.insert({
            'id': 1,
            'username': 'admin',
            'password_hash': generate_password_hash('admin')
        })
    app.run(debug=True)