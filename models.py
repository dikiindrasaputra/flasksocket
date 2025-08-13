from app import db
from datetime import datetime

# --- Model Pengguna ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    bio = db.Column(db.String(255), nullable=True)
    avatar_url = db.Column(db.String(200), nullable=True)
    nama_lengkap = db.Column(db.String(120), nullable=True)
    warung = db.relationship('Warung', backref='pemilik', lazy=True)

    def __repr__(self):
        return f'<User {self.username}>'

# --- Model Warung ---
class Warung(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nama = db.Column(db.String(100), nullable=False)
    deskripsi = db.Column(db.Text, nullable=True)
    pemilik_id = db.Column(db.Integer, db.ForeignKey('user.id'), unique=True, nullable=False)
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
    warung_id = db.Column(db.Integer, db.ForeignKey('warung.id'), nullable=False)

    def __repr__(self):
        return f'<Produk {self.nama}>'

# --- Model Keranjang (Shopping Cart) ---
class Keranjang(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    produk_id = db.Column(db.Integer, db.ForeignKey('produk.id'), nullable=False)
    jumlah = db.Column(db.Integer, nullable=False, default=1)
    
    user = db.relationship('User', backref='keranjang_items')
    produk = db.relationship('Produk')


class Pesanan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    # PERBAIKAN: Tambahkan kolom warung_id
    warung_id = db.Column(db.Integer, db.ForeignKey('warung.id'), nullable=False)
    tanggal = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    status = db.Column(db.String(20), default='Menunggu Pembayaran')
    alamat_pengiriman = db.Column(db.String(255))
    total_harga = db.Column(db.Float, nullable=False)
    
    # Perbaikan relasi, ini harus konsisten
    user = db.relationship('User', backref='pesanan_dibuat')
    warung = db.relationship('Warung', backref='pesanan_masuk')
    detail_pesanan = db.relationship('DetailPesanan', backref='pesanan', lazy=True)
    

# --- Model DetailPesanan (untuk mencatat produk di setiap pesanan) ---
class DetailPesanan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    pesanan_id = db.Column(db.Integer, db.ForeignKey('pesanan.id'), nullable=False)
    produk_id = db.Column(db.Integer, db.ForeignKey('produk.id'), nullable=False)
    jumlah = db.Column(db.Integer, nullable=False)
    harga_satuan = db.Column(db.Float, nullable=False)
    
    produk = db.relationship('Produk')