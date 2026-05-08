import os
import json
import uuid
import re
import logging
from datetime import datetime, timedelta
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from flask import Flask, request, redirect, url_for, session, render_template, jsonify, render_template_string
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text, func

# Инициализация Flask
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, template_folder='.')
app.secret_key = 'super_secret_key_gardarika'
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['UPLOAD_FOLDER'] = os.path.join(BASE_DIR, 'static', 'uploads')
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# --- ПОДКЛЮЧЕНИЕ К БАЗЕ ДАННЫХ ---
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///local.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- МОДЕЛИ БАЗЫ ДАННЫХ ---

class Role(db.Model):
    __tablename__ = 'roles'
    id = db.Column(db.Integer, primary_key=True)
    role_name = db.Column(db.String(50), unique=True, nullable=False)

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(120), unique=True)
    first_name = db.Column(db.String(100))
    last_name = db.Column(db.String(100))
    idrole = db.Column(db.Integer, db.ForeignKey('roles.id'))
    role = db.relationship('Role', backref='users')

    @property
    def is_admin(self):
        return self.role.role_name in ('Admin', 'SuperAdmin') if self.role else False

    @property
    def is_super_admin(self):
        return self.role.role_name == 'SuperAdmin' if self.role else False

class Specialization(db.Model):
    __tablename__ = 'specializations'
    id = db.Column(db.Integer, primary_key=True)
    # Map 'name' attribute to 'specialization_name' column in DB
    name = db.Column(db.Text, nullable=False, name='specialization_name')

class Trainer(db.Model):
    __tablename__ = 'trainers'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    lastname = db.Column(db.String(100))
    phone = db.Column(db.String(50))
    photo = db.Column(db.String(255))
    iduser = db.Column(db.Integer, db.ForeignKey('users.id'))
    idspecialization = db.Column(db.Integer, db.ForeignKey('specializations.id'))
    user = db.relationship('User', backref='trainer_profile')
    specialization = db.relationship('Specialization', backref='trainers')

    @property
    def full_name(self):
        # We ensure parts are strings and not None
        p_name = str(self.name or "Тренер")
        p_last = str(self.lastname or "")
        parts = [p_last, p_name]
        return " ".join(filter(None, [p for p in parts if p and p.strip() and p != 'None'])).strip()

    @property
    def spec_name(self):
        return self.specialization.name if self.specialization else "Не указана"

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "phone": self.phone,
            "specialization": self.spec_name
        }

class Service(db.Model):
    __tablename__ = 'services'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    duration = db.Column(db.Integer)
    price = db.Column(db.Integer)
    type = db.Column(db.String(100))
    limit = db.Column(db.Integer)
    notes = db.Column(db.Text)

    def to_dict(self):
        try:
            return {
                "id": self.id,
                "name": self.name,
                "duration": self.duration or 60,
                "price": self.price or 0,
                "type": self.type or "Индивидуальные занятия",
                "limit": self.limit,
                "notes": self.notes or ""
            }
        except Exception as e:
            print(f"DEBUG ERROR Service to_dict: {e}")
            return {"id": self.id, "name": self.name}

class Breed(db.Model):
    __tablename__ = 'breeds'
    id = db.Column(db.Integer, primary_key=True)
    # Map 'name' attribute to 'breed_name' column in DB
    name = db.Column(db.Text, nullable=False, name='breed_name')

class Horse(db.Model):
    __tablename__ = 'horses'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(100))
    birth_year = db.Column(db.Integer)
    color = db.Column(db.String(100))
    gender = db.Column(db.String(50))
    notes = db.Column(db.Text)
    photo = db.Column(db.String(255))
    idbreed = db.Column(db.Integer, db.ForeignKey('breeds.id'))
    breed = db.relationship('Breed', backref='horses')

    def to_dict(self):
        try:
            return {
                "id": self.id,
                "name": self.name,
                "status": self.status or "В работе (Здорова)",
                "year": self.birth_year or 2010,
                "breed": self.breed.name if self.breed else "",
                "color": self.color or "",
                "gender": self.gender or "Жеребец",
                "notes": self.notes or ""
            }
        except Exception as e:
            print(f"DEBUG ERROR Horse to_dict: {e}")
            return {"id": self.id, "name": self.name}

class Rider(db.Model):
    __tablename__ = 'riders'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    lastname = db.Column(db.String(100))
    datebirth = db.Column(db.Date)
    phone = db.Column(db.String(50))
    subscription_status = db.Column(db.String(255))
    subscription_balance = db.Column(db.Integer, default=0)
    rental_balance = db.Column(db.Integer, default=0)
    notes = db.Column(db.Text)
    photo = db.Column(db.String(255))
    iduser = db.Column(db.Integer, db.ForeignKey('users.id'))
    user = db.relationship('User', backref='rider_profile')
    
    @property
    def status(self):
        return self.subscription_status or "Без абонемента (разовые)"

    @property
    def full_name(self):
        p_name = str(self.name or "Всадник")
        p_last = str(self.lastname or "")
        parts = [p_last, p_name]
        return " ".join(filter(None, [p for p in parts if p and p.strip() and p != 'None'])).strip()

    def to_dict(self):
        try:
            return {
                "id": self.id,
                "name": self.name,
                "phone": self.phone or "",
                "status": self.subscription_status or "Без абонемента (разовые)",
                "subscription_balance": self.subscription_balance or 0,
                "rental_balance": self.rental_balance or 0,
                "dob": self.datebirth.strftime('%Y-%m-%d') if self.datebirth else "",
                "notes": self.notes or ""
            }
        except Exception as e:
            print(f"DEBUG ERROR Rider to_dict: {e}")
            return {"id": self.id, "name": self.name}

class Workout(db.Model):
    __tablename__ = 'workouts'
    id = db.Column(db.Integer, primary_key=True)
    datetime_start = db.Column(db.DateTime, nullable=False)
    idtrainer = db.Column(db.Integer, db.ForeignKey('trainers.id'))
    idservice = db.Column(db.Integer, db.ForeignKey('services.id'))
    status = db.Column(db.Text)
    notes = db.Column(db.Text)
    
    @property
    def date(self):
        return self.datetime_start.strftime('%d.%m.%Y') if self.datetime_start else ""

    @property
    def time(self):
        return self.datetime_start.strftime('%H:%M') if self.datetime_start else ""

    @property
    def iso_date(self):
        return self.datetime_start.strftime('%Y-%m-%d') if self.datetime_start else ""

    @property
    def iso_time(self):
        return self.datetime_start.strftime('%H:%M') if self.datetime_start else ""

    @property
    def rider(self):
        if not self.participants:
            return "Не назначен"
        p = self.participants[0]
        name = p.rider.full_name if p.idrider else p.guest_name
        if len(self.participants) > 1:
            return f"{name} (+{len(self.participants)-1})"
        return name

    @property
    def trainer(self):
        return self.trainer_rel.full_name if self.trainer_rel else "Без тренера"

    @property
    def horse(self):
        if not self.participants:
            return "Не выбрана"
        p = self.participants[0]
        h = p.horse.name if p.idhorse else "Своя"
        if len(self.participants) > 1:
            return h
        return h

    @property
    def service(self):
        return self.service_rel.name if self.service_rel else "Не указана"
    
    trainer_rel = db.relationship('Trainer', backref='workouts')
    service_rel = db.relationship('Service', backref='workouts')
    
    participants = db.relationship('WorkoutParticipant', backref='workout', cascade='all, delete-orphan')

class WorkoutParticipant(db.Model):
    __tablename__ = 'workout_participants'
    id = db.Column(db.Integer, primary_key=True)
    idworkout = db.Column(db.Integer, db.ForeignKey('workouts.id'))
    idrider = db.Column(db.Integer, db.ForeignKey('riders.id'), nullable=True)
    idhorse = db.Column(db.Integer, db.ForeignKey('horses.id'), nullable=True)
    guest_name = db.Column(db.String(100), nullable=True)
    rider = db.relationship('Rider', backref='participations')
    horse = db.relationship('Horse', backref='participations')

# --- АВТОРИЗАЦИЯ И ОБЩАЯ ЛОГИКА ---

def get_msk_now():
    # Возвращает текущее время по московскому времени (UTC+3)
    return datetime.utcnow() + timedelta(hours=3)

def sync_workout_statuses():
    """Синхронизирует статусы тренировок в PostgreSQL."""
    try:
        db.session.execute(text("SELECT fn_auto_update_workouts()"))
        db.session.commit()
    except Exception as e:
        print(f"DEBUG ERROR sync_workout_statuses: {e}")
        db.session.rollback()

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.context_processor
def inject_user():
    user = None
    is_admin = False
    is_super_admin = False
    if 'username' in session:
        u = User.query.filter_by(username=session['username']).first()
        if u:
            user = u.username
            is_admin = u.is_admin
            is_super_admin = u.is_super_admin
            session['is_admin'] = is_admin
            session['is_super_admin'] = is_super_admin
    return {'current_user': user, 'is_admin': is_admin, 'is_super_admin': is_super_admin}

@app.route('/')
def index():
    if 'username' in session: return redirect(url_for('dashboard_view'))
    return redirect(url_for('login'))


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard_view():
    sync_workout_statuses()
    
    # Пытаемся получить статистику из представления
    try:
        res = db.session.execute(text("SELECT * FROM v_dashboard_stats")).fetchone()
        stats = {
            'riders': res.riders_count,
            'horses': res.horses_count,
            'workouts': res.scheduled_count
        }
    except Exception as e:
        print(f"DEBUG: View v_dashboard_stats failed, using fallback: {e}")
        stats = {
            'riders': Rider.query.count(),
            'horses': Horse.query.count(),
            'workouts': Workout.query.filter(Workout.status == 'Запланировано').count()
        }
        
    workouts = Workout.query.order_by(Workout.datetime_start.asc()).all()
    return render_template('dashboard.html', stats=stats, workouts=workouts)

@app.route('/admin/users')
@login_required
def admin_users():
    current_u = User.query.filter_by(username=session.get('username')).first()
    if not current_u or not current_u.is_super_admin: return "Отказано", 403
    users = User.query.all()
    return render_template('admin-users.html', users=users)

@app.route('/make_admin/<target_username>', methods=['POST'])
@login_required
def make_admin(target_username):
    # Check directly from DB for security
    current_u = User.query.filter_by(username=session.get('username')).first()
    if not current_u or not current_u.is_super_admin: return "Отказано", 403
    u = User.query.filter_by(username=target_username).first()
    if u:
        admin_role = Role.query.filter_by(role_name='Admin').first()
        if admin_role:
            u.idrole = admin_role.id
            db.session.commit()
    return redirect(url_for('admin_users'))

@app.route('/remove_admin/<target_username>', methods=['POST'])
@login_required
def remove_admin(target_username):
    current_u = User.query.filter_by(username=session.get('username')).first()
    if not current_u or not current_u.is_super_admin: return "Отказано", 403
    u = User.query.filter_by(username=target_username).first()
    if u:
        if u.role and u.role.role_name == 'SuperAdmin': return "Нельзя", 403
        rider_role = Role.query.filter_by(role_name='Rider').first()
        if rider_role:
            u.idrole = rider_role.id
            db.session.commit()
    return redirect(url_for('admin_users'))

@app.route('/admin/delete_user/<int:user_id>', methods=['POST'])
@login_required
def delete_user(user_id):
    current_u = User.query.filter_by(username=session.get('username')).first()
    if not current_u or not current_u.is_super_admin: return "Отказано", 403
    u = User.query.get_or_404(user_id)
    if u.is_super_admin: return "Нельзя удалить СуперАдмина", 403
    
    # Detach from Rider/Trainer profiles instead of deleting them to keep history
    for rider in Rider.query.filter_by(iduser=u.id).all():
        rider.iduser = None
    for trainer in Trainer.query.filter_by(iduser=u.id).all():
        trainer.iduser = None
        
    db.session.delete(u)
    db.session.commit()
    return redirect(url_for('admin_users'))


# ===== ЛОШАДИ =====
@app.route('/horses')
@login_required
def horses_list():
    return render_template('horses-list.html', horses=Horse.query.all())

@app.route('/horses/add', methods=['GET', 'POST'])
@login_required
def horses_add():
    if not session.get('is_admin'): return "Отказано", 403
    if request.method == 'POST':
        breed_name = request.form.get('breed', 'Неизвестна')
        breed = Breed.query.filter_by(name=breed_name).first() or Breed(name=breed_name)
        if not breed.id: db.session.add(breed); db.session.commit()
        
        photo = request.files.get('photo')
        photo_name = ''
        if photo and photo.filename:
            photo_name = str(uuid.uuid4()) + '.' + photo.filename.rsplit('.', 1)[-1]
            photo.save(os.path.join(app.config['UPLOAD_FOLDER'], photo_name))
            
        horse = Horse(
            name=request.form.get('name'), 
            status=request.form.get('status', 'В работе (Здорова)'), 
            birth_year=int(request.form.get('year', 2010)) if request.form.get('year') else 2010, 
            color=request.form.get('color', ''),
            gender=request.form.get('gender', ''),
            notes=request.form.get('notes', ''),
            photo=photo_name, 
            idbreed=breed.id
        )
        db.session.add(horse); db.session.commit()
        return redirect(url_for('horses_list'))
    return render_template('horses.html')

@app.route('/horses/edit/<int:item_id>', methods=['GET', 'POST'])
@login_required
def horses_edit(item_id):
    if not session.get('is_admin'): return "Отказано", 403
    horse = Horse.query.get_or_404(item_id)
    if request.method == 'POST':
        horse.name = request.form.get('name')
        horse.status = request.form.get('status')
        horse.birth_year = int(request.form.get('year')) if request.form.get('year') else horse.birth_year
        horse.color = request.form.get('color')
        horse.gender = request.form.get('gender')
        horse.notes = request.form.get('notes')
        breed_name = request.form.get('breed')
        if breed_name:
            breed = Breed.query.filter_by(name=breed_name).first() or Breed(name=breed_name)
            if not breed.id: db.session.add(breed); db.session.commit()
            horse.idbreed = breed.id
        photo = request.files.get('photo')
        if photo and photo.filename:
            photo_name = str(uuid.uuid4()) + '.' + photo.filename.rsplit('.', 1)[-1]
            photo.save(os.path.join(app.config['UPLOAD_FOLDER'], photo_name))
            horse.photo = photo_name
        db.session.commit()
        return redirect(url_for('horses_list'))
    
    print(f"DEBUG: Handling GET for horses/edit/{item_id}")
    try:
        data = {
            "id": horse.id,
            "name": horse.name,
            "status": horse.status or "В работе (Здорова)",
            "year": horse.birth_year or 2010,
            "breed": horse.breed.name if horse.breed else "",
            "color": horse.color or "",
            "gender": horse.gender or "Жеребец",
            "notes": horse.notes or ""
        }
        print(f"DEBUG: Horse data success: {data['name']}")
        return render_template('horses.html', item=data)
    except Exception as e:
        print(f"DEBUG ERROR in horses_edit: {e}")
        return f"Ошибка: {e}", 500

@app.route('/horses/delete/<int:item_id>', methods=['POST'])
@login_required
def horses_delete(item_id):
    if not session.get('is_admin'): return "Отказано", 403
    horse = Horse.query.get_or_404(item_id)
    db.session.delete(horse); db.session.commit()
    return redirect(url_for('horses_list'))

# ===== ТРЕНЕРЫ =====
@app.route('/trainers')
@login_required
def trainers_list():
    return render_template('trainers-list.html', trainers=Trainer.query.all())

@app.route('/trainers/add', methods=['GET', 'POST'])
@login_required
def trainers_add():
    if not session.get('is_admin'): return "Отказано", 403
    if request.method == 'POST':
        spec_name = request.form.get('specialization', 'Общая')
        spec = Specialization.query.filter_by(name=spec_name).first() or Specialization(name=spec_name)
        if not spec.id: db.session.add(spec); db.session.commit()
        photo = request.files.get('photo')
        photo_name = ''
        if photo and photo.filename:
            photo_name = str(uuid.uuid4()) + '.' + photo.filename.rsplit('.', 1)[-1]
            photo.save(os.path.join(app.config['UPLOAD_FOLDER'], photo_name))
        trainer = Trainer(name=request.form.get('name'), lastname=request.form.get('lastname', ''), phone=request.form.get('phone', ''), photo=photo_name, idspecialization=spec.id)
        db.session.add(trainer); db.session.commit()
        return redirect(url_for('trainers_list'))
    return render_template('trainers.html')

@app.route('/trainers/edit/<int:item_id>', methods=['GET', 'POST'])
@login_required
def trainers_edit(item_id):
    if not session.get('is_admin'): return "Отказано", 403
    trainer = Trainer.query.get_or_404(item_id)
    if request.method == 'POST':
        trainer.name = request.form.get('name')
        trainer.lastname = request.form.get('lastname')
        trainer.phone = request.form.get('phone')
        spec_name = request.form.get('specialization')
        if spec_name:
            spec = Specialization.query.filter_by(name=spec_name).first() or Specialization(name=spec_name)
            if not spec.id: db.session.add(spec); db.session.commit()
            trainer.idspecialization = spec.id
        photo = request.files.get('photo')
        if photo and photo.filename:
            photo_name = str(uuid.uuid4()) + '.' + photo.filename.rsplit('.', 1)[-1]
            photo.save(os.path.join(app.config['UPLOAD_FOLDER'], photo_name))
            trainer.photo = photo_name
        db.session.commit()
        return redirect(url_for('trainers_list'))
    
    print(f"DEBUG: Handling GET for trainers/edit/{item_id}")
    try:
        data = {
            "id": trainer.id,
            "name": trainer.name,
            "lastname": trainer.lastname or "",
            "phone": trainer.phone or "",
            "specialization": trainer.spec_name
        }
        print(f"DEBUG: Trainer data success: {data['name']}")
        return render_template('trainers.html', item=data)
    except Exception as e:
        print(f"DEBUG ERROR in trainers_edit: {e}")
        return f"Ошибка: {e}", 500

@app.route('/trainers/delete/<int:item_id>', methods=['POST'])
@login_required
def trainers_delete(item_id):
    if not session.get('is_admin'): return "Отказано", 403
    trainer = Trainer.query.get_or_404(item_id)
    db.session.delete(trainer); db.session.commit()
    return redirect(url_for('trainers_list'))

# ===== ВСАДНИКИ =====
@app.route('/riders')
@login_required
def riders_list():
    return render_template('riders-list.html', riders=Rider.query.all())

@app.route('/riders/add', methods=['GET', 'POST'])
@login_required
def riders_add():
    if not session.get('is_admin'): return "Отказано", 403
    if request.method == 'POST':
        photo = request.files.get('photo')
        photo_name = ''
        if photo and photo.filename:
            photo_name = str(uuid.uuid4()) + '.' + photo.filename.rsplit('.', 1)[-1]
            photo.save(os.path.join(app.config['UPLOAD_FOLDER'], photo_name))
        dob_str = request.form.get('dob')
        try:
            dob = datetime.strptime(dob_str, '%Y-%m-%d').date() if dob_str and dob_str.strip() else None
        except (ValueError, TypeError):
            dob = None

        rider = Rider(
            name=request.form.get('name'), 
            phone=request.form.get('phone', ''), 
            datebirth=dob,
            subscription_status=request.form.get('status', 'Без абонемента (разовые)'),
            notes=request.form.get('notes', ''),
            photo=photo_name
        )
        db.session.add(rider); db.session.commit()
        return redirect(url_for('riders_list'))
    return render_template('riders.html')

@app.route('/riders/edit/<int:item_id>', methods=['GET', 'POST'])
@login_required
def riders_edit(item_id):
    if not session.get('is_admin'): return "Отказано", 403
    rider = Rider.query.get_or_404(item_id)
    if request.method == 'POST':
        rider.name = request.form.get('name')
        rider.phone = request.form.get('phone')
        
        dob_str = request.form.get('dob')
        try:
            rider.datebirth = datetime.strptime(dob_str, '%Y-%m-%d').date() if dob_str and dob_str.strip() else None
        except (ValueError, TypeError):
            rider.datebirth = None

        rider.subscription_status = request.form.get('status')
        rider.notes = request.form.get('notes')
        photo = request.files.get('photo')
        if photo and photo.filename:
            photo_name = str(uuid.uuid4()) + '.' + photo.filename.rsplit('.', 1)[-1]
            photo.save(os.path.join(app.config['UPLOAD_FOLDER'], photo_name))
            rider.photo = photo_name
        db.session.commit()
        return redirect(url_for('riders_list'))
    
    print(f"DEBUG: Handling GET for riders/edit/{item_id}")
    try:
        data = {
            "id": rider.id,
            "name": rider.name,
            "phone": rider.phone or "",
            "status": rider.subscription_status or "Без абонемента (разовые)",
            "dob": rider.datebirth.strftime('%Y-%m-%d') if rider.datebirth else "",
            "notes": rider.notes or ""
        }
        print(f"DEBUG: Rider data success: {data['name']}")
        return render_template('riders.html', item=data)
    except Exception as e:
        print(f"DEBUG ERROR in riders_edit: {e}")
        return f"Ошибка: {e}", 500

@app.route('/riders/<int:item_id>/subscription', methods=['POST'])
@login_required
def rider_add_subscription(item_id):
    if not session.get('is_admin'): return "Отказано", 403
    
    amount_str = request.form.get('amount', '0')
    amount = int(amount_str) if amount_str and amount_str.strip() else 0
    sub_type = request.form.get('type') # 'Subscription' or 'Rental'
    
    if request.form.get('subscription') == 'Нет абонемента':
        db.session.execute(text("UPDATE riders SET subscription_balance = 0, rental_balance = 0, subscription_status = '' WHERE id = :id"), {"id": item_id})
    else:
        db.session.execute(text("CALL sp_adjust_rider_balance(:id, :amount, CAST(:type AS TEXT))"), 
                         {"id": item_id, "amount": amount, "type": sub_type})
    
    db.session.commit()
    return redirect(url_for('riders_list'))

@app.route('/riders/<int:item_id>/adjust_balance', methods=['POST'])
@login_required
def rider_adjust_balance(item_id):
    if not session.get('is_admin'): return jsonify({"error": "Отказано"}), 403
    
    b_type = request.form.get('type') # 'sub' or 'rental'
    delta = int(request.form.get('delta', 0))
    
    # Mapper logic for JS to SQL 
    sql_type = 'Subscription' if b_type == 'sub' else 'Rental'
    
    db.session.execute(text("CALL sp_adjust_rider_balance(:id, :amount, CAST(:type AS TEXT))"), 
                     {"id": item_id, "amount": delta, "type": sql_type})
    db.session.commit()
    
    # Получаем обновленные данные для возврата в JS
    rider = Rider.query.get(item_id)
    return jsonify({
        "subscription_balance": rider.subscription_balance,
        "rental_balance": rider.rental_balance,
        "status_text": rider.subscription_status or "Добавить+"
    })

# ===== УСЛУГИ =====
@app.route('/services')
@login_required
def services_list():
    return render_template('services-list.html', services=Service.query.all())

@app.route('/services/add', methods=['GET', 'POST'])
@login_required
def services_add():
    if not session.get('is_admin'): return "Отказано", 403
    if request.method == 'POST':
        s = Service(
            name=request.form.get('name'), 
            duration=int(request.form.get('duration', 60)) if request.form.get('duration') else 60, 
            price=int(request.form.get('price', 0)) if request.form.get('price') else 0, 
            type=request.form.get('type'),
            limit=int(request.form.get('limit')) if request.form.get('limit') else None,
            notes=request.form.get('notes', '')
        )
        db.session.add(s); db.session.commit()
        return redirect(url_for('services_list'))
    return render_template('services.html')

@app.route('/services/edit/<int:item_id>', methods=['GET', 'POST'])
@login_required
def services_edit(item_id):
    if not session.get('is_admin'): return "Отказано", 403
    service = Service.query.get_or_404(item_id)
    if request.method == 'POST':
        service.name = request.form.get('name')
        service.duration = int(request.form.get('duration', 60)) if request.form.get('duration') else 60
        service.price = int(request.form.get('price', 0)) if request.form.get('price') else 0
        service.type = request.form.get('type')
        service.limit = int(request.form.get('limit')) if request.form.get('limit') else None
        service.notes = request.form.get('notes')
        db.session.commit()
        return redirect(url_for('services_list'))
    
    print(f"DEBUG: Handling GET for services/edit/{item_id}")
    try:
        data = {
            "id": service.id,
            "name": service.name,
            "duration": service.duration or 60,
            "price": service.price or 0,
            "type": service.type or "Индивидуальные занятия",
            "limit": service.limit,
            "notes": service.notes or ""
        }
        print(f"DEBUG: Service data success: {data['name']}")
        return render_template('services.html', item=data)
    except Exception as e:
        print(f"DEBUG ERROR in services_edit: {e}")
        return f"Ошибка: {e}", 500

@app.route('/services/delete/<int:item_id>', methods=['POST'])
@login_required
def services_delete(item_id):
    if not session.get('is_admin'): return "Отказано", 403
    service = Service.query.get_or_404(item_id)
    db.session.delete(service); db.session.commit()
    return redirect(url_for('services_list'))

# ===== ТРЕНИРОВКИ =====


@app.route('/workouts')
@login_required
def workouts_list():
    sync_workout_statuses()
    selected_date = request.args.get('date')
    show_all = request.args.get('all') == 'true'
    
    today = get_msk_now().strftime('%Y-%m-%d')
    effective_date = selected_date or today
    
    if show_all:
        workouts = Workout.query.order_by(Workout.datetime_start.desc()).all()
    else:
        workouts = Workout.query.filter(db.func.date(Workout.datetime_start) == effective_date).order_by(Workout.datetime_start.asc()).all()
    
    return render_template('workouts-list.html', workouts=workouts, current_date=effective_date, show_all=show_all)


@app.route('/workouts/add', methods=['GET', 'POST'])
@login_required
def workouts_add():
    if not session.get('is_admin'): return "Отказано", 403
    if request.method == 'POST':
        dt = datetime.strptime(f"{request.form.get('date')} {request.form.get('time')}", '%Y-%m-%d %H:%M')
        w = Workout(
            datetime_start=dt, 
            idtrainer=int(request.form.get('trainer')) if request.form.get('trainer') else None, 
            idservice=int(request.form.get('service')) if request.form.get('service') else None, 
            status=request.form.get('status', 'Запланировано'), 
            notes=request.form.get('notes', '')
        )
        db.session.add(w)
        db.session.flush() # Получаем ID тренировки
        
        # Обработка участников
        p_riders = request.form.getlist('p_rider[]')
        p_guests = request.form.getlist('p_guest[]')
        p_horses = request.form.getlist('p_horse[]')
        
        for i in range(len(p_riders)):
            p = WorkoutParticipant(idworkout=w.id)
            if p_riders[i] == 'guest':
                p.guest_name = p_guests[i] if i < len(p_guests) else "Гость"
            else:
                p.idrider = int(p_riders[i]) if p_riders[i] else None
            
            p.idhorse = int(p_horses[i]) if i < len(p_horses) and p_horses[i] else None
            db.session.add(p)
            
        # Если статус сразу "Завершено", списание произойдет автоматически через триггер БД
            
        db.session.commit()
        return redirect(url_for('workouts_list'))
    
    # Defaults in MSK (UTC+3)
    now_msk = datetime.utcnow() + timedelta(hours=3)
    default_date = now_msk.strftime('%Y-%m-%d')
    default_time = now_msk.strftime('%H:%M')

    return render_template('dashboard-add.html', 
                          trainers=Trainer.query.all(), 
                          riders=Rider.query.all(), 
                          horses=Horse.query.all(), 
                          services=Service.query.all(),
                          default_date=default_date,
                          default_time=default_time)

@app.route('/workouts/edit/<int:item_id>', methods=['GET', 'POST'])
@login_required
def workouts_edit(item_id):
    if not session.get('is_admin'): return "Отказано", 403
    w = Workout.query.get_or_404(item_id)
    if request.method == 'POST':
        old_status = w.status
        w.datetime_start = datetime.strptime(f"{request.form.get('date')} {request.form.get('time')}", '%Y-%m-%d %H:%M')
        w.idtrainer = int(request.form.get('trainer')) if request.form.get('trainer') else None
        w.idservice = int(request.form.get('service')) if request.form.get('service') else None
        w.status = request.form.get('status')
        w.notes = request.form.get('notes')
        
        # Если статус изменился на "Завершено", списание произойдет автоматически через триггер БД
        
        # Обновление участников
        WorkoutParticipant.query.filter_by(idworkout=w.id).delete()
        p_riders = request.form.getlist('p_rider[]')
        p_guests = request.form.getlist('p_guest[]')
        p_horses = request.form.getlist('p_horse[]')
        
        for i in range(len(p_riders)):
            p = WorkoutParticipant(idworkout=w.id)
            if p_riders[i] == 'guest':
                p.guest_name = p_guests[i] if i < len(p_guests) else "Гость"
            else:
                p.idrider = int(p_riders[i]) if p_riders[i] else None
            
            p.idhorse = int(p_horses[i]) if i < len(p_horses) and p_horses[i] else None
            db.session.add(p)
            
        db.session.commit()
        db.session.commit()
        return redirect(url_for('workouts_list'))
    
    # Подготовка данных для редактирования (JSON для JS)
    p_data = []
    for p in w.participants:
        p_data.append({
            'rider_id': p.idrider if p.idrider else 'guest',
            'guest_name': p.guest_name or '',
            'horse_id': p.idhorse or ''
        })
    return render_template('dashboard-add.html', item=w, participants_json=json.dumps(p_data), trainers=Trainer.query.all(), riders=Rider.query.all(), horses=Horse.query.all(), services=Service.query.all())

@app.route('/workouts/delete/<int:item_id>', methods=['POST'])
@login_required
def workouts_delete(item_id):
    if not session.get('is_admin'): return "Отказано", 403
    w = Workout.query.get_or_404(item_id)
    db.session.delete(w); db.session.commit()
    return redirect(url_for('workouts_list'))

@app.route('/workouts/<int:item_id>/status', methods=['POST'])
@login_required
def workouts_update_status(item_id):
    if not session.get('is_admin'): return "Отказано", 403
    w = Workout.query.get_or_404(item_id)
    old_status = w.status
    w.status = request.form.get('status')
    # Списание произойдет автоматически через триггер БД
    db.session.commit()
    return redirect(url_for('workouts_list'))

# --- АБОНЕМЕНТЫ ---
def _inflect_lessons(n):
    if n % 10 == 1 and n % 100 != 11: return f'{n} занятие'
    elif 2 <= n % 10 <= 4 and not (12 <= n % 100 <= 14): return f'{n} занятия'
    return f'{n} занятий'


# --- AUTH TEMPLATES AS STRINGS ---
CSS_STYLE = """<link rel="icon" type="image/png" href="/static/img/favicon.png"><meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no"><style>:root { --primary: #2C4A3B; --primary-light: #4A7059; --bg-color: #F4F7F6; --surface: #FFFFFF; --text-main: #1F2937; --text-muted: #6B7280; --border: #E5E7EB; --accent: #D4AF37; } * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Inter', sans-serif; } body { background-color: var(--bg-color); color: var(--text-main); display: flex; align-items: center; justify-content: center; height: 100vh; } .auth-container { background: var(--surface); padding: 40px; border-radius: 16px; border: 1px solid var(--border); box-shadow: 0 4px 6px -1px rgba(0,0,0,0.02); width: 100%; max-width: 420px; } .auth-title { font-size: 24px; font-weight: 600; margin-bottom: 24px; text-align: center; color: var(--text-main); } .logo { font-size: 20px; font-weight: 700; color: var(--primary); margin-bottom: 24px; display: flex; justify-content: center; align-items: center; gap: 12px; letter-spacing: 0.5px; text-transform: uppercase; text-decoration: none; } .logo img { width: 36px; height: 36px; object-fit: contain; border-radius: 8px; } .form-group { margin-bottom: 16px; } .form-group label { display: block; font-size: 13px; font-weight: 500; color: var(--text-muted); margin-bottom: 6px; } .form-group input { width: 100%; padding: 10px 12px; border: 1px solid var(--border); border-radius: 8px; font-size: 14px; outline: none; transition: border-color 0.2s; } .form-group input:focus { border-color: var(--primary); } .btn-primary { background-color: var(--primary); color: white; padding: 12px; border-radius: 8px; font-size: 14px; font-weight: 500; border: none; cursor: pointer; width: 100%; margin-top: 8px; transition: background-color 0.2s; } .btn-primary:hover { background-color: var(--primary-light); } .alert { padding: 12px; border-radius: 8px; margin-bottom: 16px; font-size: 13px; font-weight: 500; } .alert-error { background-color: #FEE2E2; color: #991B1B; border: 1px solid #FCA5A5; }</style>"""

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        u = User.query.filter_by(username=request.form.get('username')).first()
        if u and check_password_hash(u.password, request.form.get('password')):
            session['username'] = u.username
            return redirect(url_for('dashboard_view'))
        return render_template_string(f"<!DOCTYPE html><html><head>{CSS_STYLE}</head><body><div class='auth-container'><div class='logo'><img src='/static/img/logo.png' alt='Logo'><span>Гардарика</span></div><h1 class='auth-title'>Вход</h1><div class='alert alert-error'>Неверные данные</div><form method='POST'><div class='form-group'><label>Логин</label><input type='text' name='username' required></div><div class='form-group'><label>Пароль</label><input type='password' name='password' required></div><button type='submit' class='btn-primary'>Войти</button></form><div style='text-align:center;margin-top:20px;'><a href='/register' style='color:var(--primary);text-decoration:none;font-size:14px;'>Нет аккаунта? Зарегистрироваться</a></div></div></body></html>")
    return render_template_string(f"<!DOCTYPE html><html><head>{CSS_STYLE}</head><body><div class='auth-container'><div class='logo'><img src='/static/img/logo.png' alt='Logo'><span>Гардарика</span></div><h1 class='auth-title'>Вход</h1><form method='POST'><div class='form-group'><label>Логин</label><input type='text' name='username' required></div><div class='form-group'><label>Пароль</label><input type='password' name='password' required></div><button type='submit' class='btn-primary'>Войти</button></form><div style='text-align:center;margin-top:20px;'><a href='/register' style='color:var(--primary);text-decoration:none;font-size:14px;'>Нет аккаунта? Зарегистрироваться</a></div></div></body></html>")

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if User.query.filter_by(username=username).first():
            return render_template_string(f"<!DOCTYPE html><html><head>{CSS_STYLE}</head><body><div class='auth-container'><div class='logo'><img src='/static/img/logo.png' alt='Logo'><span>Гардарика</span></div><h1 class='auth-title'>Регистрация</h1><div class='alert alert-error'>Логин занят</div><form method='POST'><div class='form-group'><label>Логин</label><input type='text' name='username' required></div><div class='form-group'><label>Пароль</label><input type='password' name='password' required></div><button type='submit' class='btn-primary'>Зарегистрироваться</button></form><div style='text-align:center;margin-top:20px;'><a href='/login' style='color:var(--primary);text-decoration:none;font-size:14px;'>Уже есть аккаунт? Войти</a></div></div></body></html>")
        
        rider_role = Role.query.filter_by(role_name='Rider').first()
        u = User(username=username, password=generate_password_hash(password), idrole=rider_role.id)
        db.session.add(u)
        db.session.commit()
        session['username'] = username
        return redirect(url_for('dashboard_view'))
    return render_template_string(f"<!DOCTYPE html><html><head>{CSS_STYLE}</head><body><div class='auth-container'><div class='logo'><img src='/static/img/logo.png' alt='Logo'><span>Гардарика</span></div><h1 class='auth-title'>Регистрация</h1><form method='POST'><div class='form-group'><label>Логин</label><input type='text' name='username' required></div><div class='form-group'><label>Пароль</label><input type='password' name='password' required></div><button type='submit' class='btn-primary'>Зарегистрироваться</button></form><div style='text-align:center;margin-top:20px;'><a href='/login' style='color:var(--primary);text-decoration:none;font-size:14px;'>Уже есть аккаунт? Войти</a></div></div></body></html>")

def initialize_database():
    with app.app_context():
        # Определяем тип базы данных
        is_postgres = 'postgresql' in app.config['SQLALCHEMY_DATABASE_URI']
        
        # 1. Создаем таблицы (если их нет)
        db.create_all()

        # 3. Сид ролей
        if not Role.query.first():
            db.session.add_all([Role(role_name=n) for n in ["SuperAdmin", "Admin", "Trainer", "Rider"]])
            db.session.commit()

        # 4. Создаем представление статистики
        try:
            db.session.execute(text("DROP VIEW IF EXISTS v_dashboard_stats CASCADE;"))
            db.session.execute(text("""
                CREATE VIEW v_dashboard_stats AS
                SELECT 
                    (SELECT COUNT(*) FROM riders) AS riders_count,
                    (SELECT COUNT(*) FROM horses) AS horses_count,
                    (SELECT COUNT(*) FROM workouts WHERE status = 'Запланировано') AS scheduled_count;
            """))
            db.session.commit()
        except Exception as e:
            print(f"Failed to create view v_dashboard_stats: {e}")

        # 5. Создаем функции и триггеры (только для Postgres)
        if is_postgres:
            try:

                # 5.1. Функция автообновления статусов
                db.session.execute(text("""
                    CREATE FUNCTION fn_auto_update_workouts() 
                    RETURNS void AS $$
                    BEGIN
                        -- Запланировано -> Проводится
                        UPDATE workouts 
                        SET status = 'Проводится' 
                        WHERE status = 'Запланировано' AND datetime_start <= NOW() AT TIME ZONE 'UTC+3';

                        -- Проводится -> Завершено (на основе длительности услуги)
                        UPDATE workouts w
                        SET status = 'Завершено'
                        FROM services s
                        WHERE w.idservice = s.id 
                          AND w.status = 'Проводится' 
                          AND (w.datetime_start + (s.duration * interval '1 minute')) <= NOW() AT TIME ZONE 'UTC+3';
                    END;
                    $$ LANGUAGE plpgsql;
                """))

                # 5.2. Функция синхронизации текстового статуса всадника
                db.session.execute(text("""
                    CREATE FUNCTION fn_sync_rider_status_text(r_id INTEGER) 
                    RETURNS void AS $$
                    DECLARE
                        sub_bal INTEGER;
                        rent_bal INTEGER;
                        status_text TEXT := '';
                    BEGIN
                        SELECT subscription_balance, rental_balance INTO sub_bal, rent_bal FROM riders WHERE id = r_id;
                        
                        IF COALESCE(sub_bal, 0) > 0 THEN
                            status_text := 'Абонемент (' || sub_bal || ' зан.)';
                        END IF;
                        
                        IF COALESCE(rent_bal, 0) > 0 THEN
                            IF status_text != '' THEN status_text := status_text || ' + '; END IF;
                            status_text := status_text || 'Аренда (' || rent_bal || ' зан.)';
                        END IF;
                        
                        IF status_text = '' THEN status_text := 'Закончился'; END IF;
                        
                        UPDATE riders SET subscription_status = status_text WHERE id = r_id;
                    END;
                    $$ LANGUAGE plpgsql;
                """))

                # 5.3. Процедура для корректировки баланса
                db.session.execute(text("""
                    CREATE PROCEDURE sp_adjust_rider_balance(r_id INTEGER, amount INTEGER, b_type TEXT)
                    AS $$
                    BEGIN
                        IF b_type = 'Subscription' THEN
                            UPDATE riders 
                            SET subscription_balance = GREATEST(0, COALESCE(subscription_balance, 0) + amount)
                            WHERE id = r_id;
                        ELSIF b_type = 'Rental' THEN
                            UPDATE riders 
                            SET rental_balance = GREATEST(0, COALESCE(rental_balance, 0) + amount)
                            WHERE id = r_id;
                        END IF;
                        
                        -- Обновляем текстовый статус
                        PERFORM fn_sync_rider_status_text(r_id);
                    END;
                    $$ LANGUAGE plpgsql;
                """))

                # 5.3. Триггерная функция для списания занятий
                db.session.execute(text("""
                    CREATE FUNCTION fn_deduct_lessons_trigger() 
                    RETURNS TRIGGER AS $$
                    DECLARE
                        r_id INTEGER;
                        cur_sub INTEGER;
                    BEGIN
                        -- Обрабатываем как замену статуса, так и создание уже завершенной тренировки
                        IF (TG_OP = 'INSERT' AND NEW.status = 'Завершено') OR 
                           (TG_OP = 'UPDATE' AND (OLD.status IS NULL OR OLD.status != 'Завершено') AND NEW.status = 'Завершено') THEN
                            
                            FOR r_id IN SELECT idrider FROM workout_participants WHERE idworkout = NEW.id AND idrider IS NOT NULL LOOP
                                SELECT subscription_balance INTO cur_sub FROM riders WHERE id = r_id;
                                
                                IF COALESCE(cur_sub, 0) > 0 THEN
                                    UPDATE riders SET subscription_balance = subscription_balance - 1 WHERE id = r_id;
                                ELSE
                                    UPDATE riders SET rental_balance = GREATEST(0, COALESCE(rental_balance, 0) - 1) WHERE id = r_id;
                                END IF;
                                
                                PERFORM fn_sync_rider_status_text(r_id);
                            END LOOP;
                        END IF;
                        RETURN NEW;
                    END;
                    $$ LANGUAGE plpgsql;
                """))

                # 5.4. Создание ОГРАНИЧИТЕЛЬНОГО триггера (Constraint Trigger)
                db.session.execute(text("""
                    CREATE CONSTRAINT TRIGGER trg_on_workout_complete
                    AFTER INSERT OR UPDATE ON workouts
                    DEFERRABLE INITIALLY DEFERRED
                    FOR EACH ROW
                    EXECUTE FUNCTION fn_deduct_lessons_trigger();
                """))

                db.session.commit()
                print("Database triggers and functions initialized successfully.")
            except Exception as e:
                print(f"Failed to initialize database triggers/functions: {e}")
                db.session.rollback()

        # 6. Представление для активных абонементов
        try:
            db.session.execute(text("DROP VIEW IF EXISTS v_rider_active_subscriptions CASCADE;"))
            db.session.execute(text("""
                CREATE VIEW v_rider_active_subscriptions AS
                SELECT id, name, subscription_balance, rental_balance, subscription_status
                FROM riders
                WHERE COALESCE(subscription_balance, 0) > 0 OR COALESCE(rental_balance, 0) > 0;
            """))
            db.session.commit()
        except Exception as e:
            print(f"Failed to create view v_rider_active_subscriptions: {e}")

# Инициализация при запуске (только для главного процесса или прямого запуска)
if os.environ.get('GUNICORN_MAIN') == '1' or __name__ == '__main__':
    initialize_database()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
