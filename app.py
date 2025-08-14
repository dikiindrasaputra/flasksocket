import os
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
import jwt
from dotenv import load_dotenv
from flask_cors import CORS
from functools import wraps
import uuid
from flask_socketio import SocketIO, emit, join_room

# Muat variabel lingkungan dari .env
load_dotenv()

app = Flask(__name__)
CORS(app)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

FLASK_RUN_HOST = os.getenv('FLASK_RUN_HOST', '192.168.11.246')
FLASK_RUN_PORT = os.getenv('FLASK_RUN_PORT', '5001')

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
socketio = SocketIO(app, cors_allowed_origins="*")
@socketio.on('join')
def on_join(data):
    warung_id = data.get('warung_id')
    if warung_id:
        join_room(f'warung_{warung_id}')
        emit('joined_room', {'room': f'warung_{warung_id}'})


# --- Model Pengguna ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True, index=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True) # Indeks di email
    password_hash = db.Column(db.String(128), nullable=False)
    bio = db.Column(db.String(255), nullable=True)
    avatar_url = db.Column(db.String(200), nullable=True)
    nama_lengkap = db.Column(db.String(120), nullable=True)
    # Hapus index=True dari sini
    warung = db.relationship('Warung', backref='pemilik', lazy=True)

    def __repr__(self):
        return f'<User {self.username}>'
        
# --- Model Warung ---
class Warung(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nama = db.Column(db.String(100), nullable=False)
    deskripsi = db.Column(db.Text, nullable=True)
    pemilik_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True) # Indeks di foreign key
    # Hapus index=True dari sini
    produk = db.relationship('Produk', backref='warung', lazy=True)

    def __repr__(self):
        return f'<Warung {self.nama}>'

# --- Model Produk ---
class Produk(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nama = db.Column(db.String(100), nullable=False)
    deskripsi = db.Column(db.Text, nullable=True)
    harga = db.Column(db.Float, nullable=False)
    stok = db.Column(db.Integer, nullable=False)
    gambar_url = db.Column(db.String(200), nullable=True)
    warung_id = db.Column(db.Integer, db.ForeignKey('warung.id'), nullable=False, index=True) # Indeks di foreign key

    def __repr__(self):
        return f'<Produk {self.nama}>'

# --- Model Keranjang (Shopping Cart) ---
class Keranjang(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True) # Indeks di foreign key
    produk_id = db.Column(db.Integer, db.ForeignKey('produk.id'), nullable=False, index=True) # Indeks di foreign key
    jumlah = db.Column(db.Integer, nullable=False, default=1)
    
    # Hapus index=True dari sini
    user = db.relationship('User', backref='keranjang_items')
    produk = db.relationship('Produk')

# --- Model Pesanan ---
class Pesanan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True) # Indeks di foreign key
    warung_id = db.Column(db.Integer, db.ForeignKey('warung.id'), nullable=False, index=True) # Indeks di foreign key
    tanggal = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    status = db.Column(db.String(20), default='Menunggu Pembayaran', index=True)
    alamat_pengiriman = db.Column(db.String(255))
    total_harga = db.Column(db.Float, nullable=False)
    
    # Hapus index=True dari sini
    user = db.relationship('User', backref='pesanan_dibuat')
    warung = db.relationship('Warung', backref='pesanan_masuk')
    detail_pesanan = db.relationship('DetailPesanan', backref='pesanan', lazy=True)
    
# --- Model Detail Pesanan ---
class DetailPesanan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    pesanan_id = db.Column(db.Integer, db.ForeignKey('pesanan.id'), nullable=False, index=True) # Indeks di foreign key
    produk_id = db.Column(db.Integer, db.ForeignKey('produk.id'), nullable=False, index=True) # Indeks di foreign key
    jumlah = db.Column(db.Integer, nullable=False)
    harga_satuan = db.Column(db.Float, nullable=False)
    
    # Hapus index=True dari sini
    produk = db.relationship('Produk')

# Buat database jika belum ada
with app.app_context():
    db.create_all()

# --- Middleware Otentikasi ---
def token_required(f):
    @wraps(f)
    def decorator(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            token = request.headers['Authorization'].split(" ")[1]

        if not token:
            return jsonify({'message': 'Token is missing!'}), 401
        
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            current_user = User.query.filter_by(id=data['user_id']).first()
            if not current_user:
                return jsonify({'message': 'Token is invalid!'}), 401
        except Exception as e:
            print(f"Token error: {e}")
            return jsonify({'message': 'Token is invalid!'}), 401
        
        return f(current_user, *args, **kwargs)
    return decorator

# --- Endpoint Registrasi & Login (seperti sebelumnya) ---
@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')

    if not all([username, email, password]):
        return jsonify({'error': 'Missing username, email, or password'}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({'error': 'Email already exists'}), 400
    
    hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
    
    new_user = User(username=username, email=email, password_hash=hashed_password)
    db.session.add(new_user)
    db.session.commit()

    return jsonify({'message': 'User registered successfully!', 'user_id': new_user.id}), 201

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    user = User.query.filter_by(email=email).first()

    if not user or not bcrypt.check_password_hash(user.password_hash, password):
        return jsonify({'error': 'Invalid email or password'}), 401

    token_payload = {
        'user_id': user.id,
        'exp': datetime.utcnow() + timedelta(minutes=30)
    }
    token = jwt.encode(token_payload, app.config['SECRET_KEY'], algorithm="HS256")
    
    return jsonify({
        'message': 'Login successful!',
        'token': token
    }), 200

@app.route('/api/upload_avatar', methods=['POST'])
@token_required
def upload_avatar(current_user):
    # Gabungkan dua pemeriksaan awal menjadi satu untuk kode yang lebih bersih.
    # Periksa apakah 'avatar' ada dan apakah nama file tidak kosong.
    if 'avatar' not in request.files or request.files['avatar'].filename == '':
        return jsonify({'error': 'No file part or no selected file'}), 400
    
    file = request.files['avatar']
    
    # Hasilkan nama file unik
    file_extension = os.path.splitext(file.filename)[1]
    unique_filename = str(uuid.uuid4()) + file_extension
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
    
    # Simpan file ke sistem file server
    try:
        file.save(filepath)
    except Exception as e:
        return jsonify({'error': f'Failed to save file: {str(e)}'}), 500
        
    # Buat URL publik untuk gambar
    # Objek 'request' sekarang tersedia secara global karena impor di atas
    avatar_url = f"{request.scheme}://{request.host}/{app.config['UPLOAD_FOLDER']}/{unique_filename}"
    
    # Optional: Update user's avatar_url in the database
    # current_user.avatar_url = avatar_url
    # db.session.commit()
    
    return jsonify({'avatar_url': avatar_url}), 200

# Endpoint untuk menyajikan file statis dari folder 'uploads'
@app.route('/uploads/<filename>')
def serve_uploads(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


# --- Endpoint Profil (seperti sebelumnya) ---
@app.route('/api/profile', methods=['GET'])
@token_required
def get_profile(current_user):
    """
    Mengambil data profil pengguna saat ini.
    """
    # Pastikan current_user ada dan memiliki id
    if current_user is None or current_user.id is None:
        return jsonify({'message': 'User profile not found'}), 404
        
    return jsonify({
        'user_data': {
            'id': current_user.id, # Pastikan id tidak null
            'username': current_user.username,
            'email': current_user.email,
            'bio': current_user.bio,
            'avatar_url': current_user.avatar_url,
            'nama_lengkap': current_user.nama_lengkap
        }
    }), 200

@app.route('/api/profile', methods=['PUT', 'PATCH'])
@token_required
def update_profile(current_user):
    data = request.get_json()

    if 'username' in data:
        current_user.username = data['username']
    if 'bio' in data:
        current_user.bio = data['bio']
    if 'nama_lengkap' in data:
        current_user.nama_lengkap = data['nama_lengkap']
    # Perbarui avatar_url dari permintaan
    if 'avatar_url' in data:
        current_user.avatar_url = data['avatar_url']
    
    db.session.commit()

    return jsonify({
        'message': 'User profile updated successfully!',
        'user_data': {
            'user_id': current_user.id,
            'username': current_user.username,
            'email': current_user.email,
            'bio': current_user.bio,
            'avatar_url': current_user.avatar_url,
            'nama_lengkap': current_user.nama_lengkap
        }
    }), 200

@app.route('/api/warung', methods=['POST'])
@token_required
def add_warung(current_user):
    """
    Menambahkan warung baru.
    """
    data = request.get_json()
    
    nama = data.get('nama')
    deskripsi = data.get('deskripsi')
    
    if not nama or not deskripsi:
        return jsonify({'message': 'Missing required fields: nama and deskripsi'}), 400
    new_warung = Warung(
        nama=nama,
        deskripsi=deskripsi,
        pemilik_id=current_user.id
    )

    db.session.add(new_warung)
    db.session.commit()
    
    return jsonify({
        'message': 'Warung created successfully',
        'id': new_warung.id,
        'nama': new_warung.nama,
        'deskripsi': new_warung.deskripsi,
        'pemilik_id': new_warung.pemilik_id
    }), 201

@app.route('/api/warung/<int:warung_id>', methods=['PUT'])
@token_required
def update_warung(current_user, warung_id):
    """
    Mengupdate detail warung tertentu.
    """
    warung = Warung.query.get(warung_id)
    if not warung:
        return jsonify({'message': 'Warung not found'}), 404

    # Pastikan pengguna yang login adalah pemilik warung
    if warung.pemilik_id != current_user.id:
        return jsonify({'message': 'Unauthorized: You are not the owner of this warung'}), 403

    data = request.get_json()
    warung.nama = data.get('nama', warung.nama)
    warung.deskripsi = data.get('deskripsi', warung.deskripsi)
    
    db.session.commit()
    
    return jsonify({
        'message': 'Warung updated successfully',
        'warung': {
            'id': warung.id,
            'nama': warung.nama,
            'deskripsi': warung.deskripsi,
            'pemilik_id': warung.pemilik_id
        }
    }), 200

@app.route('/api/warung/<int:warung_id>', methods=['DELETE'])
@token_required
def delete_warung(current_user, warung_id):
    """
    Menghapus warung tertentu.
    """
    warung = Warung.query.get(warung_id)
    if not warung:
        return jsonify({'message': 'Warung not found'}), 404

    # Pastikan pengguna yang login adalah pemilik warung
    if warung.pemilik_id != current_user.id:
        return jsonify({'message': 'Unauthorized: You are not the owner of this warung'}), 403

    # Hapus semua produk terkait di warung ini
    for produk in warung.produk:
        db.session.delete(produk)

    db.session.delete(warung)
    db.session.commit()
    
    return jsonify({'message': 'Warung and all its products deleted successfully'}), 200

@app.route('/api/warung/<int:warung_id>', methods=['GET'])
def get_warung(warung_id):
    warung = Warung.query.get(warung_id)
    if not warung:
        return jsonify({'error': 'Warung not found'}), 404

    produk_list = []
    for produk in warung.produk:
        produk_list.append({
            'id': produk.id,
            'nama': produk.nama,
            'deskripsi': produk.deskripsi,
            'harga': produk.harga,
            'stok': produk.stok,
            'gambar_url': produk.gambar_url
        })

    return jsonify({
        'warung': {
            'id': warung.id,
            'nama': warung.nama,
            'deskripsi': warung.deskripsi,
            'pemilik': warung.pemilik.username,
            'produk': produk_list
        }
    }), 200


#  endpoint publik untuk semua warung
@app.route('/api/warung', methods=['GET'])
def get_all_warung():
    warung_list = Warung.query.all()
    output = []
    for warung in warung_list:
        output.append({
            'id': warung.id,
            'nama': warung.nama,
            'deskripsi': warung.deskripsi,
            'pemilik': warung.pemilik.username
        })
    return jsonify({'warung': output}), 200


#  endpoint private (hanya warung milik user login)
@app.route('/api/mywarung', methods=['GET'])
@token_required
def get_my_warung(current_user):
    """
    Mengambil semua warung milik pengguna yang sedang login.
    """
    user_warungs = Warung.query.filter_by(pemilik_id=current_user.id).all()

    if not user_warungs:
        return jsonify([]), 200

    warungs_list = []
    for warung in user_warungs:
        warungs_list.append({
            'id': warung.id,
            'nama': warung.nama,
            'deskripsi': warung.deskripsi,
            'pemilik_id': warung.pemilik_id,
        })

    return jsonify(warungs_list), 200

@app.route('/api/warung/<int:warung_id>/produk', methods=['GET'])
def get_produk_by_warung(warung_id):
    """
    Mengambil semua produk dari warung tertentu.
    """
    warung = Warung.query.get(warung_id)
    if not warung:
        return jsonify([]), 200 # Kembalikan array kosong jika warung tidak ditemukan

    produk_list = []
    for produk in warung.produk:
        produk_list.append({
            'id': produk.id,
            'nama': produk.nama,
            'deskripsi': produk.deskripsi,
            'harga': produk.harga,
            'stok': produk.stok,
            'gambar_url': produk.gambar_url
        })
    
    return jsonify(produk_list), 200

@app.route('/api/produk', methods=['POST'])
@token_required
def add_produk(current_user):
    """
    Menambahkan produk baru ke warung milik pengguna.
    """
    data = request.get_json()
    
    warung_id = data.get('warung_id')
    nama = data.get('nama')
    deskripsi = data.get('deskripsi')
    harga = data.get('harga')
    stok = data.get('stok')

    if not all([warung_id, nama, deskripsi, harga, stok]):
        return jsonify({'message': 'Missing required fields'}), 400

    warung = Warung.query.get(warung_id)
    if not warung:
        return jsonify({'message': 'Warung not found'}), 404

    # Pastikan pengguna yang login adalah pemilik warung
    if warung.pemilik_id != current_user.id:
        return jsonify({'message': 'Unauthorized: You are not the owner of this warung'}), 403

    new_produk = Produk(
        nama=nama,
        deskripsi=deskripsi,
        harga=harga,
        stok=stok,
        warung_id=warung_id
    )

    db.session.add(new_produk)
    db.session.commit()

    return jsonify({
        'message': 'Produk created successfully',
        'id': new_produk.id,
        'nama': new_produk.nama,
        'deskripsi': new_produk.deskripsi,
        'harga': new_produk.harga,
        'stok': new_produk.stok,
        'warung_id': new_produk.warung_id
    }), 201

# --- ENDPOINT PRODUK ---
@app.route('/api/warung/produk', methods=['POST'])
@token_required
def create_produk(current_user):
    if not current_user.warung:
        return jsonify({'error': 'User does not own a warung'}), 403

    data = request.get_json()
    nama = data.get('nama')
    deskripsi = data.get('deskripsi')
    harga = data.get('harga')
    stok = data.get('stok')
    gambar_url = data.get('gambar_url')

    if not all([nama, harga, stok is not None]):
        return jsonify({'error': 'Missing required fields: nama, harga, stok'}), 400
    
    new_produk = Produk(
        nama=nama,
        deskripsi=deskripsi,
        harga=harga,
        stok=stok,
        gambar_url=gambar_url,
        warung=current_user.warung
    )
    db.session.add(new_produk)
    db.session.commit()

    return jsonify({'message': 'Product created successfully!', 'produk_id': new_produk.id}), 201

@app.route('/api/produk/<int:produk_id>', methods=['DELETE'])
@token_required
def delete_produk(current_user, produk_id):
    """
    Menghapus produk berdasarkan ID. Hanya pemilik warung yang bisa melakukannya.
    """
    produk = Produk.query.get(produk_id)
    
    if not produk:
        return jsonify({'message': 'Produk not found'}), 404

    # Periksa apakah pengguna yang login adalah pemilik warung tempat produk ini berada
    if produk.warung.pemilik_id != current_user.id:
        return jsonify({'message': 'Unauthorized: You are not the owner of this product'}), 403

    db.session.delete(produk)
    db.session.commit()
    return jsonify({'message': 'Produk deleted successfully'}), 200

# --- ENDPOINT KERANJANG & TRANSAKSI ---
@app.route('/api/keranjang/add', methods=['POST'])
@token_required
def add_to_cart(current_user):
    data = request.get_json()
    produk_id = data.get('produk_id')
    jumlah = data.get('jumlah', 1)

    produk = Produk.query.get(produk_id)
    if not produk:
        return jsonify({'error': 'Product not found'}), 404
    
    if produk.stok < jumlah:
        return jsonify({'error': 'Insufficient stock'}), 400

    # Cek apakah produk sudah ada di keranjang user
    keranjang_item = Keranjang.query.filter_by(user_id=current_user.id, produk_id=produk.id).first()
    if keranjang_item:
        keranjang_item.jumlah += jumlah
    else:
        keranjang_item = Keranjang(user_id=current_user.id, produk_id=produk.id, jumlah=jumlah)
        db.session.add(keranjang_item)
    
    db.session.commit()
    
    return jsonify({'message': 'Product added to cart successfully!'}), 200

@app.route('/api/produk/<int:produk_id>', methods=['PUT'])
@token_required
def update_produk(current_user, produk_id):
    """
    Mengupdate produk berdasarkan ID. Hanya pemilik warung yang bisa melakukannya.
    """
    data = request.get_json()
    
    produk = Produk.query.get(produk_id)
    
    if not produk:
        return jsonify({'message': 'Produk not found'}), 404

    # Periksa apakah pengguna yang login adalah pemilik warung tempat produk ini berada
    if produk.warung.pemilik_id != current_user.id:
        return jsonify({'message': 'Unauthorized: You are not the owner of this product'}), 403

    # Perbarui field yang disediakan dalam body request
    if 'nama' in data:
        produk.nama = data['nama']
    if 'deskripsi' in data:
        produk.deskripsi = data['deskripsi']
    if 'harga' in data:
        produk.harga = data['harga']
    if 'stok' in data:
        produk.stok = data['stok']
    if 'gambar_url' in data:
        produk.gambar_url = data['gambar_url']

    db.session.commit()
    
    return jsonify({
        'message': 'Produk updated successfully',
        'id': produk.id,
        'nama': produk.nama,
        'deskripsi': produk.deskripsi,
        'harga': produk.harga,
        'stok': produk.stok,
        'warung_id': produk.warung_id
    }), 200

@app.route('/api/keranjang', methods=['GET'])
@token_required
def view_cart(current_user):
    keranjang_items = Keranjang.query.filter_by(user_id=current_user.id).all()
    output = []
    total_harga = 0
    for item in keranjang_items:
        output.append({
            'produk_id': item.produk.id,
            'nama_produk': item.produk.nama,
            'harga_satuan': item.produk.harga,
            'jumlah': item.jumlah,
            'subtotal': item.produk.harga * item.jumlah
        })
        total_harga += item.produk.harga * item.jumlah
    
    return jsonify({
        'keranjang': output,
        'total_harga': total_harga
    }), 200

@app.route('/api/keranjang/checkout', methods=['POST'])
@token_required
def checkout(current_user):
    keranjang_items = Keranjang.query.filter_by(user_id=current_user.id).all()
    data = request.get_json()
    alamat_pengiriman = data.get('shipping_address')
    status_awal = data.get('status', 'Menunggu Pembayaran') # Mendapatkan status dari request, dengan fallback 'Menunggu Pembayaran'

    if not keranjang_items:
        return jsonify({"message": "Keranjang Anda kosong"}), 400

    if not alamat_pengiriman:
        return jsonify({"message": "Alamat pengiriman tidak boleh kosong"}), 400

    # Kelompokkan item keranjang berdasarkan warung
    items_by_warung = {}
    for item in keranjang_items:
        produk = Produk.query.get(item.produk_id)
        if not produk:
            return jsonify({"message": "Produk tidak ditemukan"}), 404
        
        # Cek stok
        if produk.stok < item.jumlah:
            return jsonify({"message": f"Stok produk {produk.nama} tidak mencukupi"}), 400

        warung_id = produk.warung_id
        if warung_id not in items_by_warung:
            items_by_warung[warung_id] = []
        items_by_warung[warung_id].append(item)

    # Buat pesanan terpisah untuk setiap warung
    list_pesanan_baru = []
    for warung_id, items in items_by_warung.items():
        total_harga_pesanan = 0
        for item in items:
            produk = Produk.query.get(item.produk_id)
            total_harga_pesanan += produk.harga * item.jumlah

        new_pesanan = Pesanan(
            user_id=current_user.id,
            warung_id=warung_id,
            alamat_pengiriman=alamat_pengiriman,
            total_harga=total_harga_pesanan,
            status=status_awal # Menggunakan status dari request
        )
        db.session.add(new_pesanan)
        db.session.flush()

        # Tambahkan detail pesanan dan kurangi stok
        for item in items:
            produk = Produk.query.get(item.produk_id)
            detail_pesanan = DetailPesanan(
                pesanan_id=new_pesanan.id,
                produk_id=produk.id,
                jumlah=item.jumlah,
                harga_satuan=produk.harga
            )
            db.session.add(detail_pesanan)
            produk.stok -= item.jumlah

        list_pesanan_baru.append(new_pesanan)

    # Hapus item dari keranjang
    for item in keranjang_items:
        db.session.delete(item)

    db.session.commit()

    # Kirim notifikasi ke setiap warung yang terlibat
    for pesanan in list_pesanan_baru:
        socketio.emit('new_order_alert', {
            'pesanan_id': pesanan.id,
            'pemesan': current_user.username,
            'total_harga': pesanan.total_harga,
            'warung_id': pesanan.warung_id,
            'warung_nama': pesanan.warung.nama
        }, room=f'warung_{pesanan.warung_id}')
    
    return jsonify({"message": f"{len(list_pesanan_baru)} pesanan berhasil dibuat."}), 200

@app.route('/api/checkout/local', methods=['POST'])
@token_required
def checkout_local(current_user):
    """
    Checkout dengan data keranjang yang dikirim dari client (local cart).
    Tidak menggunakan keranjang yang tersimpan di server.
    """
    data = request.get_json()
    
    # Validasi input
    if not data:
        return jsonify({"success": False, "message": "Data tidak valid"}), 400
    
    items = data.get('items', [])
    alamat_pengiriman = data.get('alamat_pengiriman')
    warung_id = data.get('warung_id')
    total_harga_client = data.get('total_harga', 0)
    
    if not items:
        return jsonify({"success": False, "message": "Keranjang kosong"}), 400
    
    if not alamat_pengiriman:
        return jsonify({"success": False, "message": "Alamat pengiriman harus diisi"}), 400
    
    if not warung_id:
        return jsonify({"success": False, "message": "Warung ID tidak valid"}), 400
    
    # Validasi warung exists
    warung = Warung.query.get(warung_id)
    if not warung:
        return jsonify({"success": False, "message": "Warung tidak ditemukan"}), 404
    
    try:
        # Validasi dan hitung ulang total harga
        total_harga_server = 0
        validated_items = []
        
        for item in items:
            produk_id = item.get('produk_id')
            jumlah = item.get('jumlah')
            harga_satuan_client = item.get('harga_satuan')
            
            if not all([produk_id, jumlah, harga_satuan_client]):
                return jsonify({
                    "success": False, 
                    "message": "Data item tidak lengkap"
                }), 400
            
            # Validasi produk
            produk = Produk.query.get(produk_id)
            if not produk:
                return jsonify({
                    "success": False, 
                    "message": f"Produk dengan ID {produk_id} tidak ditemukan"
                }), 404
            
            # Validasi produk belongs to warung
            if produk.warung_id != warung_id:
                return jsonify({
                    "success": False, 
                    "message": f"Produk {produk.nama} bukan milik warung ini"
                }), 400
            
            # Validasi stok
            if produk.stok < jumlah:
                return jsonify({
                    "success": False, 
                    "message": f"Stok produk {produk.nama} tidak mencukupi. Stok tersedia: {produk.stok}"
                }), 400
            
            # Validasi harga (untuk keamanan)
            if abs(produk.harga - harga_satuan_client) > 0.01:  # Toleransi 1 sen
                return jsonify({
                    "success": False, 
                    "message": f"Harga produk {produk.nama} tidak sesuai"
                }), 400
            
            subtotal = produk.harga * jumlah
            total_harga_server += subtotal
            
            validated_items.append({
                'produk': produk,
                'jumlah': jumlah,
                'harga_satuan': produk.harga,
                'subtotal': subtotal
            })
        
        # Validasi total harga (toleransi 1 rupiah)
        if abs(total_harga_server - total_harga_client) > 1:
            return jsonify({
                "success": False, 
                "message": f"Total harga tidak sesuai. Server: {total_harga_server}, Client: {total_harga_client}"
            }), 400
        
        # Buat pesanan baru
        new_pesanan = Pesanan(
            user_id=current_user.id,
            warung_id=warung_id,
            alamat_pengiriman=alamat_pengiriman,
            total_harga=total_harga_server,
            status='Menunggu Pembayaran'
        )
        db.session.add(new_pesanan)
        db.session.flush()  # Untuk mendapatkan ID pesanan
        
        # Tambahkan detail pesanan dan kurangi stok
        for item_data in validated_items:
            produk = item_data['produk']
            jumlah = item_data['jumlah']
            harga_satuan = item_data['harga_satuan']
            
            # Buat detail pesanan
            detail_pesanan = DetailPesanan(
                pesanan_id=new_pesanan.id,
                produk_id=produk.id,
                jumlah=jumlah,
                harga_satuan=harga_satuan
            )
            db.session.add(detail_pesanan)
            
            # Kurangi stok
            produk.stok -= jumlah
        
        db.session.commit()
        
        # Kirim notifikasi ke warung
        socketio.emit('new_order_alert', {
            'pesanan_id': new_pesanan.id,
            'pemesan': current_user.username,
            'total_harga': new_pesanan.total_harga,
            'warung_id': new_pesanan.warung_id,
            'warung_nama': warung.nama
        }, room=f'warung_{warung_id}')
        
        return jsonify({
            "success": True,
            "message": "Pesanan berhasil dibuat",
            "pesanan_id": new_pesanan.id,
            "total_harga": total_harga_server
        }), 200
        
    except Exception as e:
        db.session.rollback()
        print(f"Error in checkout_local: {e}")
        return jsonify({
            "success": False,
            "message": "Terjadi kesalahan saat memproses pesanan"
        }), 500
@app.route('/api/transaksi', methods=['GET'])
@token_required
def get_transaksi_history(current_user):
    pesanan_user = Pesanan.query.filter_by(user_id=current_user.id).order_by(Pesanan.tanggal.desc()).all()
    
    history_list = []
    for pesanan in pesanan_user:
        detail_list = []
        for detail in pesanan.detail_pesanan:
            produk = Produk.query.get(detail.produk_id)
            detail_list.append({
                "produk_nama": produk.nama if produk else 'Produk tidak ditemukan',
                "jumlah": detail.jumlah,
                "harga_satuan": detail.harga_satuan
            })
        
        history_list.append({
            "pesanan_id": pesanan.id,
            "tanggal": pesanan.tanggal.isoformat(),
            "status": pesanan.status,
            "total_harga": pesanan.total_harga,
            "alamat_pengiriman": pesanan.alamat_pengiriman,
            "detail_pesanan": detail_list
        })
    
    return jsonify(transaksi_history=history_list)

# --- Endpoint melihat pesanan dari user ---
@app.route('/api/warung/<int:warung_id>/pesanan', methods=['GET'])
@token_required
def get_warung_orders(current_user, warung_id):
    """
    Mengambil semua pesanan yang terkait dengan warung tertentu milik pengguna yang sedang login.
    """
    warung = Warung.query.filter_by(id=warung_id, pemilik_id=current_user.id).first()
    
    if not warung:
        # Menangani kasus warung tidak ditemukan ATAU bukan milik user
        return jsonify({'message': 'Warung not found or unauthorized'}), 404

    # Ambil pesanan dengan efisien
    pesanan_warung = Pesanan.query.filter_by(warung_id=warung.id).order_by(Pesanan.tanggal.desc()).all()

    orders_by_status = {}
    for pesanan in pesanan_warung:
        detail_list = []
        for detail in pesanan.detail_pesanan:
            detail_list.append({
                "produk_nama": detail.produk.nama, # Diasumsikan relasi produk ada
                "jumlah": detail.jumlah,
                "harga_satuan": detail.harga_satuan
            })
        
        order_data = {
            "pesanan_id": pesanan.id,
            "tanggal": pesanan.tanggal.isoformat(),
            "status": pesanan.status,
            "total_harga": pesanan.total_harga,
            "alamat_pengiriman": pesanan.alamat_pengiriman,
            "pemesan": pesanan.user.username, # Diasumsikan relasi user ada
            "detail_pesanan": detail_list
        }
        
        status = pesanan.status
        if status not in orders_by_status:
            orders_by_status[status] = []
        orders_by_status[status].append(order_data)

    return jsonify(orders_by_status), 200

@app.route('/api/pesanan/<int:pesanan_id>/status', methods=['PUT'])
@token_required
def update_pesanan_status(current_user, pesanan_id):
    """
    Mengupdate status pesanan tertentu. Hanya pemilik warung yang bisa melakukannya.
    """
    pesanan = Pesanan.query.get(pesanan_id)
    if not pesanan:
        return jsonify({'message': 'Pesanan not found'}), 404

    # Periksa kepemilikan warung
    if pesanan.warung.pemilik_id != current_user.id:
        return jsonify({'message': 'Unauthorized'}), 403

    data = request.get_json()
    new_status = data.get('status')
    
    valid_statuses = ['Menunggu Pembayaran','Menunggu Konfirmasi', 'Diproses', 'Dikirim', 'Selesai', 'Dibatalkan']
    
    if new_status and new_status in valid_statuses:
        pesanan.status = new_status
        db.session.commit()
        return jsonify({'message': 'Status pesanan berhasil diupdate', 'new_status': new_status}), 200
    
    return jsonify({'message': 'Status tidak valid'}), 400
@app.route('/api/dashboard/warungs', methods=['GET'])
@token_required
def get_warung_dashboard(current_user):
    """
    Mengambil data ringkasan penjualan untuk semua warung milik pengguna.
    """
    # Ambil semua warung yang dimiliki oleh pengguna saat ini
    warungs = Warung.query.filter_by(pemilik_id=current_user.id).all()
    dashboard_data = {}

    for warung in warungs:
        # Cari semua pesanan untuk warung ini
        pesanan_list = Pesanan.query.filter_by(warung_id=warung.id).all()
        
        # Hitung metrik
        total_orders = len(pesanan_list)
        total_revenue = sum(p.total_harga for p in pesanan_list)

        # Hitung penjualan per produk
        sales_per_product = {}
        for pesanan in pesanan_list:
            for detail in pesanan.detail_pesanan:
                produk_nama = detail.produk.nama
                if produk_nama not in sales_per_product:
                    sales_per_product[produk_nama] = {
                        'total_jumlah': 0,
                        'total_pendapatan': 0.0
                    }
                sales_per_product[produk_nama]['total_jumlah'] += detail.jumlah
                sales_per_product[produk_nama]['total_pendapatan'] += detail.jumlah * detail.harga_satuan

        dashboard_data[warung.nama] = {
            'warung_id': warung.id,
            'total_pesanan': total_orders,
            'total_pendapatan': total_revenue,
            'penjualan_per_produk': sales_per_product
        }

    return jsonify(dashboard_data), 200
@app.route('/api/wallet/summary', methods=['GET'])
@token_required
def get_wallet_summary(current_user):
    """
    Mengambil ringkasan transaksi (total transaksi dan total pendapatan)
    dari semua pesanan yang sudah selesai untuk warung-warung milik pengguna.
    """
    # Dapatkan semua warung milik pengguna
    warungs = Warung.query.filter_by(pemilik_id=current_user.id).all()
    warung_ids = [w.id for w in warungs]

    if not warung_ids:
        return jsonify({'total_transaksi': 0, 'total_pendapatan': 0.0}), 200

    # Dapatkan semua pesanan yang sudah selesai dari warung-warung tersebut
    pesanan_selesai = Pesanan.query.filter(
        Pesanan.warung_id.in_(warung_ids),
        Pesanan.status == 'Selesai'
    ).all()

    total_transaksi = len(pesanan_selesai)
    total_pendapatan = sum(p.total_harga for p in pesanan_selesai)

    return jsonify({
        'total_transaksi': total_transaksi,
        'total_pendapatan': total_pendapatan
    }), 200


if __name__ == '__main__':
    socketio.run(app, debug=False, host='0.0.0.0', port=5001)
