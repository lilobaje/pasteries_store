from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
from flask_mail import Mail, Message
import json
import uuid
import requests
from threading import Thread
from urllib.parse import quote

app = Flask(__name__)

def send_async_email(app, msg):
    with app.app_context():
        mail.send(msg)

def send_email(msg):
    """Run email sending in a background thread."""
    Thread(target=send_async_email, args=(app, msg)).start()

# --- Mail Configuration ---
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'your_email@gmail.com'  # Replace with your Gmail
app.config['MAIL_PASSWORD'] = 'your_app_password'      # Use App Password
app.config['MAIL_DEFAULT_SENDER'] = ('Sweet Treats Bakery', 'your_email@gmail.com')

mail = Mail(app)

# --- Configuration ---
app.config['SECRET_KEY'] = 'your_super_secret_key_change_in_production'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///pastrystore.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# WhatsApp Business Configuration
WHATSAPP_NUMBER = '2348012345678'  # Replace with your WhatsApp number (include country code, no + or spaces)

# Directory for uploaded images
UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'admin_login'
login_manager.login_message_category = 'info'

# --- Helper Functions ---
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_uploaded_file(file):
    if file and allowed_file(file.filename):
        filename_base, file_extension = os.path.splitext(secure_filename(file.filename))
        unique_filename = str(uuid.uuid4()) + file_extension
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        file.save(file_path)
        return unique_filename
    return None

def download_and_save_image(image_url):
    if not image_url:
        return None
    try:
        response = requests.get(image_url, stream=True, timeout=10)
        response.raise_for_status()
        
        content_type = response.headers.get('Content-Type')
        extension = '.jpg'
        if content_type and 'image/' in content_type:
            extension = '.' + content_type.split('/')[-1].replace('jpeg', 'jpg')
        elif '.' in image_url:
            extension = os.path.splitext(image_url)[1]

        unique_filename = str(uuid.uuid4()) + extension
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)

        with open(file_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        return unique_filename
    except Exception as e:
        print(f"Error downloading image {image_url}: {e}")
        return None

def generate_whatsapp_link(pastry_name, pastry_price):
    """Generate WhatsApp link with pre-filled message"""
    message = f"Hello! I'm interested in ordering {pastry_name} priced at ₦{pastry_price:,.0f}. Is it available?"
    encoded_message = quote(message)
    return f"https://wa.me/{WHATSAPP_NUMBER}?text={encoded_message}"

# --- Database Models ---
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Pastry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50), nullable=False)  # Cakes, Cookies, Bread, Donuts, etc.
    price = db.Column(db.Float, nullable=False)
    image = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    serving_size = db.Column(db.String(50), nullable=True)  # e.g., "Serves 10-12", "6 pieces", etc.
    available = db.Column(db.Boolean, default=True)  # Is it currently available?
    
    gallery_json = db.Column(db.Text, nullable=True)
    ingredients_json = db.Column(db.Text, nullable=True)  # List of ingredients
    allergens_json = db.Column(db.Text, nullable=True)  # List of allergens
    features_json = db.Column(db.Text, nullable=True)  # Special features (e.g., "Sugar-free", "Gluten-free")

    @property
    def gallery(self):
        return json.loads(self.gallery_json) if self.gallery_json else []

    @gallery.setter
    def gallery(self, value):
        self.gallery_json = json.dumps(value)

    @property
    def ingredients(self):
        return json.loads(self.ingredients_json) if self.ingredients_json else []

    @ingredients.setter
    def ingredients(self, value):
        self.ingredients_json = json.dumps(value)

    @property
    def allergens(self):
        return json.loads(self.allergens_json) if self.allergens_json else []

    @allergens.setter
    def allergens(self, value):
        self.allergens_json = json.dumps(value)

    @property
    def features(self):
        return json.loads(self.features_json) if self.features_json else []

    @features.setter
    def features(self, value):
        self.features_json = json.dumps(value)
    
    @property
    def image_url(self):
        return url_for('static', filename=f'uploads/{self.image}') if self.image else 'https://placehold.co/400x400/cccccc/333333?text=No+Image'

    @property
    def gallery_urls(self):
        return [url_for('static', filename=f'uploads/{filename}') for filename in self.gallery]
    
    @property
    def whatsapp_link(self):
        return generate_whatsapp_link(self.name, self.price)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- Initial Data ---
initial_pastry_data = {
    'Cakes': [
        {
            'name': 'Chocolate Fudge Cake',
            'category': 'Cakes',
            'price': 15000,
            'serving_size': 'Serves 10-12',
            'available': True,
            'image': 'https://images.unsplash.com/photo-1578985545062-69928b1d9587?w=400',
            'gallery': [
                'https://images.unsplash.com/photo-1578985545062-69928b1d9587?w=600',
                'https://images.unsplash.com/photo-1606890737304-57a1ca8a5b62?w=600'
            ],
            'description': 'Rich, moist chocolate cake with creamy fudge frosting',
            'ingredients': ['Flour', 'Cocoa powder', 'Eggs', 'Sugar', 'Butter', 'Milk', 'Vanilla extract'],
            'allergens': ['Eggs', 'Dairy', 'Gluten'],
            'features': ['Freshly baked', 'Custom message available', 'Perfect for celebrations']
        },
        {
            'name': 'Red Velvet Cake',
            'category': 'Cakes',
            'price': 18000,
            'serving_size': 'Serves 12-15',
            'available': True,
            'image': 'https://images.unsplash.com/photo-1586985289688-ca3cf47d3e6e?w=400',
            'gallery': [
                'https://images.unsplash.com/photo-1586985289688-ca3cf47d3e6e?w=600'
            ],
            'description': 'Classic red velvet with cream cheese frosting',
            'ingredients': ['Flour', 'Cocoa powder', 'Buttermilk', 'Eggs', 'Sugar', 'Cream cheese', 'Red food coloring'],
            'allergens': ['Eggs', 'Dairy', 'Gluten'],
            'features': ['Signature recipe', 'Smooth cream cheese frosting', 'Instagram-worthy']
        },
        {
            'name': 'Vanilla Sponge Cake',
            'category': 'Cakes',
            'price': 12000,
            'serving_size': 'Serves 8-10',
            'available': True,
            'image': 'https://images.unsplash.com/photo-1588195538326-c5b1e5b80c18?w=400',
            'gallery': [
                'https://images.unsplash.com/photo-1588195538326-c5b1e5b80c18?w=600'
            ],
            'description': 'Light and fluffy vanilla sponge cake with buttercream',
            'ingredients': ['Flour', 'Eggs', 'Sugar', 'Butter', 'Vanilla extract', 'Milk'],
            'allergens': ['Eggs', 'Dairy', 'Gluten'],
            'features': ['Light and fluffy', 'Perfect for any occasion', 'Can be customized']
        }
    ],
    'Cookies': [
        {
            'name': 'Chocolate Chip Cookies',
            'category': 'Cookies',
            'price': 3500,
            'serving_size': '12 pieces',
            'available': True,
            'image': 'https://images.unsplash.com/photo-1499636136210-6f4ee915583e?w=400',
            'gallery': [
                'https://images.unsplash.com/photo-1499636136210-6f4ee915583e?w=600'
            ],
            'description': 'Classic homemade chocolate chip cookies, crispy outside, chewy inside',
            'ingredients': ['Flour', 'Chocolate chips', 'Butter', 'Brown sugar', 'Eggs', 'Vanilla'],
            'allergens': ['Eggs', 'Dairy', 'Gluten'],
            'features': ['Freshly baked daily', 'Crispy edges, chewy center', 'Perfect with milk']
        },
        {
            'name': 'Oatmeal Raisin Cookies',
            'category': 'Cookies',
            'price': 3000,
            'serving_size': '12 pieces',
            'available': True,
            'image': 'https://images.unsplash.com/photo-1618897996318-5a901fa6ca71?w=400',
            'gallery': [
                'https://images.unsplash.com/photo-1618897996318-5a901fa6ca71?w=600'
            ],
            'description': 'Hearty oatmeal cookies with plump raisins',
            'ingredients': ['Oats', 'Raisins', 'Flour', 'Butter', 'Brown sugar', 'Eggs', 'Cinnamon'],
            'allergens': ['Eggs', 'Dairy', 'Gluten'],
            'features': ['Healthy option', 'No artificial flavors', 'Great for breakfast']
        }
    ],
    'Bread': [
        {
            'name': 'Artisan Sourdough Bread',
            'category': 'Bread',
            'price': 2500,
            'serving_size': '1 loaf',
            'available': True,
            'image': 'https://images.unsplash.com/photo-1509440159596-0249088772ff?w=400',
            'gallery': [
                'https://images.unsplash.com/photo-1509440159596-0249088772ff?w=600'
            ],
            'description': 'Crusty sourdough bread with a tangy flavor and chewy texture',
            'ingredients': ['Flour', 'Water', 'Salt', 'Sourdough starter'],
            'allergens': ['Gluten'],
            'features': ['No yeast added', 'Long fermentation', 'Crusty exterior']
        },
        {
            'name': 'Whole Wheat Bread',
            'category': 'Bread',
            'price': 1800,
            'serving_size': '1 loaf',
            'available': True,
            'image': 'https://images.unsplash.com/photo-1549931319-a545dcf3bc0c?w=400',
            'gallery': [
                'https://images.unsplash.com/photo-1549931319-a545dcf3bc0c?w=600'
            ],
            'description': 'Nutritious whole wheat bread, perfect for sandwiches',
            'ingredients': ['Whole wheat flour', 'Water', 'Yeast', 'Salt', 'Honey'],
            'allergens': ['Gluten'],
            'features': ['High fiber', 'No preservatives', 'Freshly baked']
        }
    ],
    'Donuts': [
        {
            'name': 'Glazed Donuts',
            'category': 'Donuts',
            'price': 2000,
            'serving_size': '6 pieces',
            'available': True,
            'image': 'https://images.unsplash.com/photo-1551024506-0bccd828d307?w=400',
            'gallery': [
                'https://images.unsplash.com/photo-1551024506-0bccd828d307?w=600'
            ],
            'description': 'Classic glazed donuts with a sweet, shiny coating',
            'ingredients': ['Flour', 'Sugar', 'Eggs', 'Milk', 'Butter', 'Yeast', 'Vanilla'],
            'allergens': ['Eggs', 'Dairy', 'Gluten'],
            'features': ['Melt-in-your-mouth', 'Perfect morning treat', 'Kids favorite']
        },
        {
            'name': 'Chocolate Frosted Donuts',
            'category': 'Donuts',
            'price': 2500,
            'serving_size': '6 pieces',
            'available': True,
            'image': 'https://images.unsplash.com/photo-1527515637462-cff94eecc1ac?w=400',
            'gallery': [
                'https://images.unsplash.com/photo-1527515637462-cff94eecc1ac?w=600'
            ],
            'description': 'Soft donuts topped with rich chocolate frosting and sprinkles',
            'ingredients': ['Flour', 'Cocoa powder', 'Sugar', 'Eggs', 'Milk', 'Butter', 'Sprinkles'],
            'allergens': ['Eggs', 'Dairy', 'Gluten'],
            'features': ['Rich chocolate flavor', 'Colorful sprinkles', 'Party favorite']
        }
    ],
    'Pastries': [
        {
            'name': 'Croissants',
            'category': 'Pastries',
            'price': 1500,
            'serving_size': '4 pieces',
            'available': True,
            'image': 'https://images.unsplash.com/photo-1555507036-ab1f4038808a?w=400',
            'gallery': [
                'https://images.unsplash.com/photo-1555507036-ab1f4038808a?w=600'
            ],
            'description': 'Buttery, flaky French croissants',
            'ingredients': ['Flour', 'Butter', 'Milk', 'Sugar', 'Yeast', 'Salt'],
            'allergens': ['Dairy', 'Gluten'],
            'features': ['Authentic French recipe', 'Layered and flaky', 'Perfect with coffee']
        },
        {
            'name': 'Meat Pies',
            'category': 'Pastries',
            'price': 2500,
            'serving_size': '6 pieces',
            'available': True,
            'image': 'https://images.unsplash.com/photo-1509042239860-f550ce710b93?w=400',
            'gallery': [
                'https://images.unsplash.com/photo-1509042239860-f550ce710b93?w=600'
            ],
            'description': 'Savory meat pies with seasoned beef filling',
            'ingredients': ['Flour', 'Ground beef', 'Onions', 'Spices', 'Butter'],
            'allergens': ['Gluten', 'Dairy'],
            'features': ['Nigerian favorite', 'Perfectly seasoned', 'Great for snacking']
        }
    ]
}

def populate_initial_data():
    with app.app_context():
        db.create_all()

        if User.query.filter_by(username='admin').first() is None:
            print("Creating default admin user...")
            admin_user = User(username='admin')
            admin_user.set_password('admin123')  # CHANGE THIS
            db.session.add(admin_user)
            db.session.commit()
            print("Default admin user created (username: admin, password: admin123)")

        if Pastry.query.count() == 0:
            print("Populating initial pastry data...")
            for category_name, pastries in initial_pastry_data.items():
                for pastry_data in pastries:
                    main_image_filename = download_and_save_image(pastry_data['image'])
                    
                    gallery_filenames = []
                    for img_url in pastry_data.get('gallery', []):
                        filename = download_and_save_image(img_url)
                        if filename:
                            gallery_filenames.append(filename)

                    pastry = Pastry(
                        name=pastry_data['name'],
                        category=pastry_data['category'],
                        price=pastry_data['price'],
                        image=main_image_filename if main_image_filename else 'placeholder.png',
                        description=pastry_data['description'],
                        serving_size=pastry_data.get('serving_size'),
                        available=pastry_data.get('available', True),
                        gallery=gallery_filenames,
                        ingredients=pastry_data.get('ingredients', []),
                        allergens=pastry_data.get('allergens', []),
                        features=pastry_data.get('features', [])
                    )
                    db.session.add(pastry)
            db.session.commit()
            print("Initial pastry data populated.")

# --- Frontend Routes ---
@app.route('/')
def home():
    featured_pastries = Pastry.query.filter_by(available=True).limit(6).all()
    categories = db.session.query(Pastry.category).distinct().all()
    categories = [c[0] for c in categories]
    return render_template('home.html', featured_pastries=featured_pastries, categories=categories)

@app.route('/pastries')
@app.route('/pastries/<category>')
def pastries(category=None):
    if category:
        pastries_list = Pastry.query.filter_by(category=category).all()
    else:
        pastries_list = Pastry.query.all()
    
    all_categories = db.session.query(Pastry.category).distinct().all()
    all_categories = [c[0] for c in all_categories]

    return render_template('pastries.html', pastries=pastries_list, category=category, 
                         all_categories=all_categories)

@app.route('/pastry/<int:pastry_id>')
def pastry_detail(pastry_id):
    pastry = Pastry.query.get_or_404(pastry_id)
    
    related_pastries = Pastry.query.filter(
        Pastry.category == pastry.category,
        Pastry.id != pastry_id
    ).limit(3).all()
    
    return render_template('pastry_detail.html', pastry=pastry, related_pastries=related_pastries)

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/contact', methods=['GET', 'POST'])
def contact():
    message_sent = False
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        subject = request.form.get('subject')
        message = request.form.get('message')

        try:
            admin_body = f"""
            📩 New Contact Message from Sweet Treats Bakery:

            👤 Name: {name}
            📧 Email: {email}
            🏷️ Subject: {subject}

            💬 Message:
            {message}
            """

            admin_msg = Message(
                subject=f"New Message: {subject}",
                recipients=['your_email@gmail.com'],
                body=admin_body
            )
            send_email(admin_msg)

            flash('Your message has been sent successfully!', 'success')
            message_sent = True
        except Exception as e:
            print(f"Email sending failed: {e}")
            flash('An error occurred. Please contact us via WhatsApp.', 'error')

    return render_template('contact.html', message_sent=message_sent, whatsapp_number=WHATSAPP_NUMBER)

# --- Admin Routes ---
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if current_user.is_authenticated:
        return redirect(url_for('admin_dashboard'))

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            login_user(user)
            flash('Logged in successfully!', 'success')
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Invalid username or password', 'error')
    return render_template('admin_login.html')

@app.route('/admin/logout')
@login_required
def admin_logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('home'))

@app.route('/admin')
@login_required
def admin_dashboard():
    total_pastries = Pastry.query.count()
    categories = db.session.query(Pastry.category).distinct().all()
    total_categories = len(categories)
    
    pastries = Pastry.query.all()
    total_value = sum(pastry.price for pastry in pastries)
    
    available = Pastry.query.filter_by(available=True).count()
    
    category_counts = {}
    for category in categories:
        count = Pastry.query.filter_by(category=category[0]).count()
        category_counts[category[0]] = count
    
    return render_template('admin_dashboard.html',
        total_pastries=total_pastries,
        total_categories=total_categories,
        total_value=total_value,
        available=available,
        category_counts=category_counts
    )

@app.route('/admin/pastries')
@app.route('/admin/pastries/<category>')
@login_required
def admin_pastries(category=None):
    all_categories = db.session.query(Pastry.category).distinct().all()
    all_categories = [c[0] for c in all_categories]
    
    if category:
        all_pastries = Pastry.query.filter_by(category=category).all()
    else:
        all_pastries = Pastry.query.all()
    
    return render_template('admin_pastries.html', pastries=all_pastries, 
                         categories=all_categories, selected_category=category)

@app.route('/admin/pastries/add', methods=['GET', 'POST'])
@login_required
def admin_add_pastry():
    all_categories = db.session.query(Pastry.category).distinct().all()
    all_categories = [c[0] for c in all_categories]

    if request.method == 'POST':
        try:
            name = request.form['name']
            price = float(request.form['price'])
            description = request.form['description']
            serving_size = request.form.get('serving_size', '')
            available = request.form.get('available') == 'on'
            
            category = request.form['category']
            if category == 'new_category':
                new_category_input = request.form.get('new_category_input', '').strip()
                if not new_category_input:
                    flash('New category name cannot be empty.', 'error')
                    return redirect(url_for('admin_add_pastry'))
                category = new_category_input
            
            main_image_file = request.files.get('image_file')
            main_image_filename = save_uploaded_file(main_image_file)
            if not main_image_filename:
                flash('No valid image file uploaded.', 'error')
                return redirect(url_for('admin_add_pastry'))

            gallery_files = request.files.getlist('gallery_files')
            gallery_filenames = []
            for file in gallery_files:
                if file.filename:
                    filename = save_uploaded_file(file)
                    if filename:
                        gallery_filenames.append(filename)
            
            new_pastry = Pastry(
                name=name,
                category=category,
                price=price,
                image=main_image_filename,
                description=description,
                serving_size=serving_size,
                available=available,
                gallery=gallery_filenames,
                ingredients=json.loads(request.form.get('ingredients', '[]')),
                allergens=json.loads(request.form.get('allergens', '[]')),
                features=json.loads(request.form.get('features', '[]'))
            )
            db.session.add(new_pastry)
            db.session.commit()
            flash(f'Pastry "{name}" added successfully!', 'success')
            return redirect(url_for('admin_pastries'))
        except Exception as e:
            flash(f'An error occurred: {e}', 'error')

    return render_template('admin_add_edit_pastry.html', pastry=None, categories=all_categories)

@app.route('/admin/pastries/edit/<int:pastry_id>', methods=['GET', 'POST'])
@login_required
def admin_edit_pastry(pastry_id):
    pastry = Pastry.query.get_or_404(pastry_id)
    all_categories = db.session.query(Pastry.category).distinct().all()
    all_categories = [c[0] for c in all_categories]

    if request.method == 'POST':
        try:
            pastry.name = request.form['name']
            pastry.price = float(request.form['price'])
            pastry.description = request.form['description']
            pastry.serving_size = request.form.get('serving_size', '')
            pastry.available = request.form.get('available') == 'on'
            
            category = request.form['category']
            if category == 'new_category':
                new_category_input = request.form.get('new_category_input', '').strip()
                if not new_category_input:
                    flash('New category name cannot be empty.', 'error')
                    return redirect(url_for('admin_edit_pastry', pastry_id=pastry_id))
                pastry.category = new_category_input
            else:
                pastry.category = category
            
            main_image_file = request.files.get('image_file')
            if main_image_file and main_image_file.filename != '':
                new_main_image = save_uploaded_file(main_image_file)
                if new_main_image:
                    pastry.image = new_main_image
            
            gallery_files = request.files.getlist('gallery_files')
            new_gallery = []
            for file in gallery_files:
                if file.filename:
                    filename = save_uploaded_file(file)
                    if filename:
                        new_gallery.append(filename)
            
            if new_gallery:
                pastry.gallery = new_gallery
            
            pastry.ingredients = json.loads(request.form.get('ingredients', '[]'))
            pastry.allergens = json.loads(request.form.get('allergens', '[]'))
            pastry.features = json.loads(request.form.get('features', '[]'))

            db.session.commit()
            flash(f'Pastry "{pastry.name}" updated successfully!', 'success')
            return redirect(url_for('admin_pastries'))
        except Exception as e:
            db.session.rollback()
            flash(f'An error occurred: {e}', 'error')

    pastry.ingredients_str = json.dumps(pastry.ingredients)
    pastry.allergens_str = json.dumps(pastry.allergens)
    pastry.features_str = json.dumps(pastry.features)

    return render_template('admin_add_edit_pastry.html', pastry=pastry, categories=all_categories)

@app.route('/admin/pastries/delete/<int:pastry_id>')
@login_required
def admin_delete_pastry(pastry_id):
    pastry = Pastry.query.get_or_404(pastry_id)
    pastry_name = pastry.name

    try:
        db.session.delete(pastry)
        db.session.commit()
        flash(f'Pastry "{pastry_name}" deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting pastry: {e}', 'error')
    
    return redirect(url_for('admin_pastries'))

if __name__ == '__main__':
    populate_initial_data()
    app.run(debug=True)