import os
import json
import uuid
import re
import logging
from datetime import datetime, timedelta
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from flask import Flask, request, redirect, url_for, session, render_template, jsonify, render_template_string, send_file
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text, func
from io import BytesIO

# Подгружаем переменные окружения из .env (DATABASE_URL и т. п.).
# Если python-dotenv не установлен — молча работаем по реальному окружению.
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))
except ImportError:
    pass

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
    # Новые поля: переехали сюда из trainers / riders, чтобы избежать дублирования
    name = db.Column(db.String(100))
    lastname = db.Column(db.String(100))
    phone = db.Column(db.String(50))
    is_approved = db.Column(db.Boolean, default=True, nullable=False)
    idrole = db.Column(db.Integer, db.ForeignKey('roles.id'))
    role = db.relationship('Role', backref='users')

    @property
    def is_admin(self):
        return self.role.role_name in ('Admin', 'SuperAdmin') if self.role else False

    @property
    def is_super_admin(self):
        return self.role.role_name == 'SuperAdmin' if self.role else False

    @property
    def is_trainer(self):
        return self.role.role_name == 'Trainer' if self.role else False

    @property
    def is_rider(self):
        return self.role.role_name == 'Rider' if self.role else False

    @property
    def full_name(self):
        parts = [(self.lastname or '').strip(), (self.name or '').strip()]
        clean = ' '.join(p for p in parts if p)
        return clean or self.username

class Specialization(db.Model):
    __tablename__ = 'specializations'
    id = db.Column(db.Integer, primary_key=True)
    # Map 'name' attribute to 'specialization_name' column in DB
    name = db.Column(db.Text, nullable=False, name='specialization_name')

class Trainer(db.Model):
    __tablename__ = 'trainers'
    id = db.Column(db.Integer, primary_key=True)
    photo = db.Column(db.String(255))
    iduser = db.Column(db.Integer, db.ForeignKey('users.id'))
    idspecialization = db.Column(db.Integer, db.ForeignKey('specializations.id'))
    user = db.relationship('User', backref='trainer_profile')
    specialization = db.relationship('Specialization', backref='trainers')

    # Имя/фамилия/телефон хранятся в users; здесь — proxy-свойства,
    # чтобы шаблоны и старый код продолжали работать как раньше.
    @property
    def name(self):
        return self.user.name if self.user else ''

    @property
    def lastname(self):
        return self.user.lastname if self.user else ''

    @property
    def phone(self):
        return self.user.phone if self.user else ''

    @property
    def full_name(self):
        if not self.user:
            return "Тренер"
        return self.user.full_name or "Тренер"

    @property
    def is_approved(self):
        return self.user.is_approved if self.user else False

    @property
    def spec_name(self):
        return self.specialization.name if self.specialization else "Не указана"

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "lastname": self.lastname,
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
    datebirth = db.Column(db.Date)
    subscription_status = db.Column(db.String(255))
    subscription_balance = db.Column(db.Integer, default=0)
    rental_balance = db.Column(db.Integer, default=0)
    notes = db.Column(db.Text)
    photo = db.Column(db.String(255))
    iduser = db.Column(db.Integer, db.ForeignKey('users.id'))
    user = db.relationship('User', backref='rider_profile')

    # Имя/фамилия/телефон теперь живут в users; на Rider — read-only proxy.
    @property
    def name(self):
        return self.user.name if self.user else ''

    @property
    def lastname(self):
        return self.user.lastname if self.user else ''

    @property
    def phone(self):
        return self.user.phone if self.user else ''

    @property
    def status(self):
        return self.subscription_status or "Без абонемента (разовые)"

    @property
    def full_name(self):
        if not self.user:
            return "Всадник"
        return self.user.full_name or "Всадник"

    def to_dict(self):
        try:
            return {
                "id": self.id,
                "name": self.name,
                "lastname": self.lastname,
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
    """Доступ только авторизованным. Гость считается авторизованным."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session and not session.get('is_guest'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    """Только администратор / суперадмин. Возвращает 403 для остальных."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('is_admin'):
            return "Отказано", 403
        return f(*args, **kwargs)
    return decorated_function


def staff_required(f):
    """Доступ для администратора и тренеров (но не для всадника/гостя)."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not (session.get('is_admin') or session.get('is_trainer')):
            return "Только для администратора и тренера", 403
        return f(*args, **kwargs)
    return decorated_function


def non_guest_required(f):
    """Любые модификации запрещены для гостя."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('is_guest'):
            return "В режиме гостя доступен только просмотр", 403
        return f(*args, **kwargs)
    return decorated_function


@app.context_processor
def inject_user():
    user = None
    is_admin = False
    is_super_admin = False
    is_trainer = False
    is_rider = False
    is_guest = bool(session.get('is_guest'))

    if 'username' in session and not is_guest:
        u = User.query.filter_by(username=session['username']).first()
        if u:
            user = u.username
            is_admin = u.is_admin
            is_super_admin = u.is_super_admin
            is_trainer = u.is_trainer
            is_rider = u.is_rider
            session['is_admin'] = is_admin
            session['is_super_admin'] = is_super_admin
            session['is_trainer'] = is_trainer
            session['is_rider'] = is_rider
    elif is_guest:
        user = 'Гость'

    return {
        'current_user': user,
        'is_admin': is_admin,
        'is_super_admin': is_super_admin,
        'is_trainer': is_trainer,
        'is_rider': is_rider,
        'is_guest': is_guest,
    }

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
    # Показываем только одобренных тренеров (заявки видны в /admin/approvals)
    trainers = (Trainer.query
                .join(User, Trainer.iduser == User.id)
                .filter(User.is_approved == True)  # noqa: E712
                .all())
    return render_template('trainers-list.html', trainers=trainers)


def _unique_username(base):
    """Подбирает свободный username вида <base>, <base>2, <base>3..."""
    if not base:
        base = 'user'
    slug = ''.join(ch for ch in base.lower() if ch.isalnum() or ch == '_')
    slug = slug or 'user'
    candidate = slug
    i = 1
    while User.query.filter_by(username=candidate).first():
        i += 1
        candidate = f"{slug}{i}"
    return candidate


@app.route('/trainers/add', methods=['GET', 'POST'])
@login_required
@admin_required
def trainers_add():
    if request.method == 'POST':
        spec_name = request.form.get('specialization', 'Общая')
        spec = Specialization.query.filter_by(name=spec_name).first() or Specialization(name=spec_name)
        if not spec.id:
            db.session.add(spec)
            db.session.commit()
        photo = request.files.get('photo')
        photo_name = ''
        if photo and photo.filename:
            photo_name = str(uuid.uuid4()) + '.' + photo.filename.rsplit('.', 1)[-1]
            photo.save(os.path.join(app.config['UPLOAD_FOLDER'], photo_name))

        # Создаём User для тренера (имя/фамилия/телефон живут в users)
        trainer_role = Role.query.filter_by(role_name='Trainer').first()
        name = request.form.get('name', '').strip()
        lastname = request.form.get('lastname', '').strip()
        phone = request.form.get('phone', '').strip()
        username = _unique_username(name or 'trainer')
        u = User(
            username=username,
            password=generate_password_hash(str(uuid.uuid4()),
                                            method='pbkdf2:sha256'),
            name=name, lastname=lastname, phone=phone,
            first_name=name, last_name=lastname,
            idrole=trainer_role.id if trainer_role else None,
            is_approved=True,  # созданного админом сразу публикуем
        )
        db.session.add(u)
        db.session.flush()

        trainer = Trainer(iduser=u.id, photo=photo_name, idspecialization=spec.id)
        db.session.add(trainer)
        db.session.commit()
        return redirect(url_for('trainers_list'))
    return render_template('trainers.html')


@app.route('/trainers/edit/<int:item_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def trainers_edit(item_id):
    trainer = Trainer.query.get_or_404(item_id)
    if request.method == 'POST':
        # Имя/фамилия/телефон редактируем у связанного users
        if trainer.user:
            trainer.user.name = request.form.get('name')
            trainer.user.lastname = request.form.get('lastname')
            trainer.user.phone = request.form.get('phone')
            trainer.user.first_name = request.form.get('name')
            trainer.user.last_name = request.form.get('lastname')
        spec_name = request.form.get('specialization')
        if spec_name:
            spec = Specialization.query.filter_by(name=spec_name).first() or Specialization(name=spec_name)
            if not spec.id:
                db.session.add(spec)
                db.session.commit()
            trainer.idspecialization = spec.id
        photo = request.files.get('photo')
        if photo and photo.filename:
            photo_name = str(uuid.uuid4()) + '.' + photo.filename.rsplit('.', 1)[-1]
            photo.save(os.path.join(app.config['UPLOAD_FOLDER'], photo_name))
            trainer.photo = photo_name
        db.session.commit()
        return redirect(url_for('trainers_list'))

    try:
        data = {
            "id": trainer.id,
            "name": trainer.name,
            "lastname": trainer.lastname or "",
            "phone": trainer.phone or "",
            "specialization": trainer.spec_name
        }
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
    riders = Rider.query.all()
    # Зарегистрированные всадники, которых ещё не «привязали» к списку.
    # Их видят только админ и тренер — чтобы добавить в список.
    linkable_users = []
    if session.get('is_admin') or session.get('is_trainer'):
        linked_ids = {r.iduser for r in riders if r.iduser}
        rider_role = Role.query.filter_by(role_name='Rider').first()
        if rider_role:
            q = (User.query
                 .filter(User.idrole == rider_role.id,
                         User.is_approved == True)  # noqa: E712
                 .all())
            linkable_users = [u for u in q if u.id not in linked_ids]
    return render_template('riders-list.html',
                           riders=riders,
                           linkable_users=linkable_users)


@app.route('/riders/add', methods=['GET', 'POST'])
@login_required
@admin_required
def riders_add():
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

        # Создаём User + Rider (имя/фамилия/телефон — в users)
        rider_role = Role.query.filter_by(role_name='Rider').first()
        name = request.form.get('name', '').strip()
        lastname = request.form.get('lastname', '').strip()
        phone = request.form.get('phone', '').strip()
        username = _unique_username(name or 'rider')
        u = User(
            username=username,
            password=generate_password_hash(str(uuid.uuid4()),
                                            method='pbkdf2:sha256'),
            name=name, lastname=lastname, phone=phone,
            first_name=name, last_name=lastname,
            idrole=rider_role.id if rider_role else None,
            is_approved=True,
        )
        db.session.add(u)
        db.session.flush()

        rider = Rider(
            iduser=u.id,
            datebirth=dob,
            subscription_status=request.form.get('status', 'Без абонемента (разовые)'),
            notes=request.form.get('notes', ''),
            photo=photo_name,
        )
        db.session.add(rider)
        db.session.commit()
        return redirect(url_for('riders_list'))
    return render_template('riders.html')


@app.route('/riders/edit/<int:item_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def riders_edit(item_id):
    rider = Rider.query.get_or_404(item_id)
    if request.method == 'POST':
        if rider.user:
            rider.user.name = request.form.get('name')
            rider.user.lastname = request.form.get('lastname')
            rider.user.phone = request.form.get('phone')
            rider.user.first_name = request.form.get('name')
            rider.user.last_name = request.form.get('lastname')

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

    try:
        data = {
            "id": rider.id,
            "name": rider.name,
            "lastname": rider.lastname or "",
            "phone": rider.phone or "",
            "status": rider.subscription_status or "Без абонемента (разовые)",
            "dob": rider.datebirth.strftime('%Y-%m-%d') if rider.datebirth else "",
            "notes": rider.notes or ""
        }
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


# ===== ВЫВОД PDF: ЧЕК ОПЛАТЫ УСЛУГ =====
@app.route('/workouts/<int:item_id>/receipt')
@login_required
def workout_receipt(item_id):
    """Генерирует PDF-чек оплаты услуг по конкретной тренировке.

    На один чек попадают: всадник(и), тренер, лошадь(и), услуга, дата/время и сумма.
    """
    w = Workout.query.get_or_404(item_id)
    pdf_bytes = build_workout_receipt_pdf(w)
    filename = f"receipt_workout_{item_id}.pdf"
    return send_file(
        BytesIO(pdf_bytes),
        mimetype='application/pdf',
        as_attachment=False,
        download_name=filename,
    )


def build_workout_receipt_pdf(w):
    """Собирает PDF-чек по тренировке. Возвращает bytes."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    # Регистрируем шрифт с поддержкой кириллицы.
    # Сначала ищем рядом с проектом (static/fonts/DejaVuSans*.ttf — лежат в репо,
    # работает на любой ОС: Windows / macOS / Linux), потом — системные пути.
    font_name = 'DejaVu'
    bold_name = 'DejaVu-Bold'
    bundled_dir = os.path.join(BASE_DIR, 'static', 'fonts')
    candidates = [
        os.path.join(bundled_dir, 'DejaVuSans.ttf'),
        '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        '/usr/share/fonts/dejavu/DejaVuSans.ttf',
        '/Library/Fonts/DejaVuSans.ttf',
        '/System/Library/Fonts/Supplemental/Arial Unicode.ttf',
    ]
    bold_candidates = [
        os.path.join(bundled_dir, 'DejaVuSans-Bold.ttf'),
        '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
        '/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf',
        '/Library/Fonts/DejaVuSans-Bold.ttf',
        '/System/Library/Fonts/Supplemental/Arial Unicode.ttf',
    ]
    regular_path = next((p for p in candidates if os.path.exists(p)), None)
    bold_path = next((p for p in bold_candidates if os.path.exists(p)), None)
    if regular_path and font_name not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(font_name, regular_path))
    if bold_path and bold_name not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(bold_name, bold_path))
    use_font = font_name if regular_path else 'Helvetica'
    use_bold = bold_name if bold_path else (font_name if regular_path else 'Helvetica-Bold')

    # Подготовка данных
    riders = []
    horses = []
    for p in w.participants:
        if p.idrider and p.rider:
            riders.append(p.rider.full_name)
        elif p.guest_name:
            riders.append(f"{p.guest_name} (гость)")
        if p.idhorse and p.horse:
            horses.append(p.horse.name)
        elif p.idrider or p.guest_name:
            horses.append('Своя')
    riders_str = ', '.join(riders) if riders else 'Не назначен'
    horses_str = ', '.join(horses) if horses else 'Не выбрана'
    trainer_str = w.trainer_rel.full_name if w.trainer_rel else 'Без тренера'
    service = w.service_rel
    service_name = service.name if service else 'Не указана'
    duration = service.duration if service and service.duration else 0
    price = service.price if service and service.price else 0
    total = price * max(1, len(riders) or 1)
    date_str = w.datetime_start.strftime('%d.%m.%Y') if w.datetime_start else '—'
    time_str = w.datetime_start.strftime('%H:%M') if w.datetime_start else '—'
    issued_str = get_msk_now().strftime('%d.%m.%Y %H:%M')
    receipt_no = f"{w.id:06d}"

    # Рисуем PDF
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    page_w, page_h = A4

    # Заголовок
    c.setFont(use_bold, 18)
    c.drawCentredString(page_w / 2, page_h - 25 * mm, 'КОННОСПОРТИВНЫЙ КЛУБ «ГАРДАРИКА»')
    c.setFont(use_font, 10)
    c.drawCentredString(page_w / 2, page_h - 32 * mm, 'Чек об оплате услуг')

    # Линия
    c.setStrokeColorRGB(0.7, 0.7, 0.7)
    c.line(20 * mm, page_h - 38 * mm, page_w - 20 * mm, page_h - 38 * mm)

    # Шапка
    c.setFont(use_bold, 12)
    c.drawString(20 * mm, page_h - 48 * mm, f'Чек № {receipt_no}')
    c.setFont(use_font, 10)
    c.drawRightString(page_w - 20 * mm, page_h - 48 * mm, f'Дата формирования: {issued_str}')

    # Содержание
    y = page_h - 60 * mm
    line_h = 8 * mm

    def row(label, value):
        nonlocal y
        c.setFont(use_bold, 10)
        c.drawString(20 * mm, y, label)
        c.setFont(use_font, 10)
        c.drawString(70 * mm, y, str(value))
        y -= line_h

    row('Всадник(и):', riders_str)
    row('Тренер:', trainer_str)
    row('Лошадь(и):', horses_str)
    row('Услуга:', service_name)
    row('Дата проведения:', f'{date_str} в {time_str}')
    row('Длительность:', f'{duration} мин' if duration else '—')
    row('Цена услуги:', f'{price} ₽')
    row('Кол-во участников:', str(max(1, len(riders) or 1)))
    row('Статус тренировки:', w.status or 'Запланировано')

    # Итог
    y -= 4 * mm
    c.setStrokeColorRGB(0.7, 0.7, 0.7)
    c.line(20 * mm, y, page_w - 20 * mm, y)
    y -= 10 * mm
    c.setFont(use_bold, 14)
    c.drawString(20 * mm, y, 'ИТОГО К ОПЛАТЕ:')
    c.drawRightString(page_w - 20 * mm, y, f'{total} ₽')

    # Подпись
    y -= 30 * mm
    c.setFont(use_font, 10)
    c.drawString(20 * mm, y, '___________________________')
    c.drawString(20 * mm, y - 6 * mm, 'Подпись администратора')

    # Футер
    c.setFont(use_font, 8)
    c.setFillColorRGB(0.5, 0.5, 0.5)
    c.drawCentredString(
        page_w / 2,
        15 * mm,
        'КСК «Гардарика» — конноспортивный клуб. Спасибо, что выбираете нас!',
    )

    c.showPage()
    c.save()
    return buf.getvalue()


# --- АБОНЕМЕНТЫ ---
def _inflect_lessons(n):
    if n % 10 == 1 and n % 100 != 11: return f'{n} занятие'
    elif 2 <= n % 10 <= 4 and not (12 <= n % 100 <= 14): return f'{n} занятия'
    return f'{n} занятий'


# --- AUTH TEMPLATES AS STRINGS ---
CSS_STYLE = """<link rel="icon" type="image/png" href="/static/img/favicon.png"><meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no"><style>:root { --primary: #2C4A3B; --primary-light: #4A7059; --bg-color: #F4F7F6; --surface: #FFFFFF; --text-main: #1F2937; --text-muted: #6B7280; --border: #E5E7EB; --accent: #D4AF37; } * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Inter', sans-serif; } body { background-color: var(--bg-color); color: var(--text-main); display: flex; align-items: center; justify-content: center; height: 100vh; } .auth-container { background: var(--surface); padding: 40px; border-radius: 16px; border: 1px solid var(--border); box-shadow: 0 4px 6px -1px rgba(0,0,0,0.02); width: 100%; max-width: 420px; } .auth-title { font-size: 24px; font-weight: 600; margin-bottom: 24px; text-align: center; color: var(--text-main); } .logo { font-size: 20px; font-weight: 700; color: var(--primary); margin-bottom: 24px; display: flex; justify-content: center; align-items: center; gap: 12px; letter-spacing: 0.5px; text-transform: uppercase; text-decoration: none; } .logo img { width: 36px; height: 36px; object-fit: contain; border-radius: 8px; } .form-group { margin-bottom: 16px; } .form-group label { display: block; font-size: 13px; font-weight: 500; color: var(--text-muted); margin-bottom: 6px; } .form-group input { width: 100%; padding: 10px 12px; border: 1px solid var(--border); border-radius: 8px; font-size: 14px; outline: none; transition: border-color 0.2s; } .form-group input:focus { border-color: var(--primary); } .btn-primary { background-color: var(--primary); color: white; padding: 12px; border-radius: 8px; font-size: 14px; font-weight: 500; border: none; cursor: pointer; width: 100%; margin-top: 8px; transition: background-color 0.2s; } .btn-primary:hover { background-color: var(--primary-light); } .alert { padding: 12px; border-radius: 8px; margin-bottom: 16px; font-size: 13px; font-weight: 500; } .alert-error { background-color: #FEE2E2; color: #991B1B; border: 1px solid #FCA5A5; }</style>"""

def _auth_layout(title, body_html, error_html=''):
    """Универсальная обёртка для страниц /login и /register."""
    return render_template_string(
        f"""<!DOCTYPE html><html><head>{CSS_STYLE}</head>
        <body><div class='auth-container'>
            <div class='logo'><img src='/static/img/logo.png' alt='Logo'><span>Гардарика</span></div>
            <h1 class='auth-title'>{title}</h1>
            {error_html}
            {body_html}
        </div></body></html>""")


def _login_form_html():
    return ("""
        <form method='POST'>
            <div class='form-group'><label>Логин</label>
                <input type='text' name='username' required></div>
            <div class='form-group'><label>Пароль</label>
                <input type='password' name='password' required></div>
            <button type='submit' class='btn-primary'>Войти</button>
        </form>
        <form method='POST' action='/login/guest' style='margin-top:12px;'>
            <button type='submit' class='btn-primary' style='background:var(--accent);'>
                Войти как гость
            </button>
        </form>
        <div style='text-align:center;margin-top:20px;'>
            <a href='/register' style='color:var(--primary);text-decoration:none;font-size:14px;'>
                Нет аккаунта? Зарегистрироваться
            </a>
        </div>""")


def _register_form_html(values=None):
    v = values or {}
    return f"""
        <form method='POST' id='regForm'>
            <div class='form-group'><label>Логин</label>
                <input type='text' name='username' value='{v.get("username","")}' required></div>
            <div class='form-group'><label>Пароль</label>
                <input type='password' name='password' required></div>
            <div class='form-group'><label>Имя</label>
                <input type='text' name='name' value='{v.get("name","")}' required></div>
            <div class='form-group'><label>Фамилия</label>
                <input type='text' name='lastname' value='{v.get("lastname","")}'></div>
            <div class='form-group'><label>Телефон</label>
                <input type='text' name='phone' value='{v.get("phone","")}'
                       placeholder='+7 (999) 000-00-00'></div>
            <div class='form-group'>
                <label style='display:block;margin-bottom:8px;'>Я регистрируюсь как:</label>
                <label style='display:block;margin-bottom:6px;font-weight:400;color:var(--text-main);'>
                    <input type='radio' name='role' value='Rider' checked
                           onchange='document.getElementById("specBlock").style.display="none"'>
                    Всадник <span style='color:var(--text-muted);font-size:12px;'>
                    (доступ сразу после регистрации)</span>
                </label>
                <label style='display:block;font-weight:400;color:var(--text-main);'>
                    <input type='radio' name='role' value='Trainer'
                           onchange='document.getElementById("specBlock").style.display="block"'>
                    Тренер <span style='color:var(--text-muted);font-size:12px;'>
                    (после одобрения администратора)</span>
                </label>
            </div>
            <div class='form-group' id='specBlock' style='display:none;'>
                <label>Специализация</label>
                <input type='text' name='specialization'
                       value='{v.get("specialization","")}'
                       placeholder='Например: Выездка, Конкур, Иппотерапия'>
            </div>
            <button type='submit' class='btn-primary'>Зарегистрироваться</button>
        </form>
        <div style='text-align:center;margin-top:20px;'>
            <a href='/login' style='color:var(--primary);text-decoration:none;font-size:14px;'>
                Уже есть аккаунт? Войти
            </a>
        </div>"""


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        password = request.form.get('password') or ''
        u = User.query.filter_by(username=username).first()
        if not u or not check_password_hash(u.password, password):
            return _auth_layout(
                'Вход', _login_form_html(),
                "<div class='alert alert-error'>Неверный логин или пароль</div>")
        if not u.is_approved:
            return _auth_layout(
                'Вход', _login_form_html(),
                "<div class='alert alert-error'>Ваша учётная запись "
                "ожидает одобрения администратора.</div>")
        session.clear()
        session['username'] = u.username
        session['is_guest'] = False
        return redirect(url_for('dashboard_view'))
    return _auth_layout('Вход', _login_form_html())


@app.route('/login/guest', methods=['POST'])
def login_guest():
    """Вход в режиме гостя: read-only сессия, без записи в БД."""
    session.clear()
    session['is_guest'] = True
    session['is_admin'] = False
    session['is_super_admin'] = False
    session['is_trainer'] = False
    session['is_rider'] = False
    return redirect(url_for('dashboard_view'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        password = request.form.get('password') or ''
        name = (request.form.get('name') or '').strip()
        lastname = (request.form.get('lastname') or '').strip()
        phone = (request.form.get('phone') or '').strip()
        role_pick = request.form.get('role', 'Rider')
        spec_name = (request.form.get('specialization') or '').strip()

        form_values = {
            'username': username, 'name': name, 'lastname': lastname,
            'phone': phone, 'specialization': spec_name,
        }

        if not username or not password or not name:
            return _auth_layout(
                'Регистрация', _register_form_html(form_values),
                "<div class='alert alert-error'>Заполните логин, пароль и имя</div>")

        if User.query.filter_by(username=username).first():
            return _auth_layout(
                'Регистрация', _register_form_html(form_values),
                "<div class='alert alert-error'>Логин занят</div>")

        if role_pick not in ('Rider', 'Trainer'):
            role_pick = 'Rider'

        role = Role.query.filter_by(role_name=role_pick).first()
        if not role:
            return _auth_layout(
                'Регистрация', _register_form_html(form_values),
                "<div class='alert alert-error'>Роль не найдена</div>")

        is_approved = (role_pick == 'Rider')

        u = User(
            username=username,
            password=generate_password_hash(password, method='pbkdf2:sha256'),
            name=name, lastname=lastname, phone=phone,
            first_name=name, last_name=lastname,
            idrole=role.id, is_approved=is_approved,
        )
        db.session.add(u)
        db.session.flush()

        # Тренер: создаём профиль сразу, но скрытый до одобрения.
        if role_pick == 'Trainer':
            spec = None
            if spec_name:
                spec = (Specialization.query.filter_by(name=spec_name).first()
                        or Specialization(name=spec_name))
                if not spec.id:
                    db.session.add(spec)
                    db.session.flush()
            db.session.add(Trainer(iduser=u.id,
                                   idspecialization=spec.id if spec else None))

        # Всадник: профиль в `riders` НЕ создаётся.
        # Запись там появится только когда тренер/админ
        # «привяжет» этого пользователя к списку всадников.

        db.session.commit()

        if not is_approved:
            return _auth_layout(
                'Регистрация',
                "<div style='text-align:center;line-height:1.6;'>"
                "<p style='font-size:15px;color:var(--text-main);margin-bottom:18px;'>"
                "Заявка тренера отправлена на рассмотрение.<br>"
                "Дождитесь подтверждения администратора.</p>"
                "<a href='/login' class='btn-primary' style='display:inline-block;"
                "text-decoration:none;padding:10px 24px;'>На страницу входа</a>"
                "</div>")

        session.clear()
        session['username'] = username
        session['is_guest'] = False
        return redirect(url_for('dashboard_view'))

    return _auth_layout('Регистрация', _register_form_html())


# ===== АДМИН: ОДОБРЕНИЕ ЗАЯВОК =====

@app.route('/admin/approvals')
@login_required
@admin_required
def admin_approvals():
    """Список незодобренных пользователей (в основном — тренеры)."""
    pending = (User.query
               .filter(User.is_approved == False)  # noqa: E712
               .order_by(User.id.desc()).all())
    return render_template('admin-approvals.html', pending=pending)


@app.route('/admin/approve/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def admin_approve(user_id):
    u = User.query.get_or_404(user_id)
    u.is_approved = True
    db.session.commit()
    return redirect(url_for('admin_approvals'))


@app.route('/admin/reject/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def admin_reject(user_id):
    u = User.query.get_or_404(user_id)
    if u.is_super_admin:
        return "Нельзя удалить суперадмина", 403
    # Каскадно убираем связанные профили (на случай неодобренного тренера)
    Trainer.query.filter_by(iduser=u.id).delete()
    Rider.query.filter_by(iduser=u.id).delete()
    db.session.delete(u)
    db.session.commit()
    return redirect(url_for('admin_approvals'))


# ===== ПРИВЯЗКА ПОЛЬЗОВАТЕЛЯ ВСАДНИКА К СПИСКУ /riders =====

@app.route('/riders/link_user', methods=['POST'])
@login_required
@staff_required
def riders_link_user():
    """Создаёт запись riders для уже зарегистрированного пользователя-всадника."""
    user_id = request.form.get('iduser')
    if not user_id:
        return redirect(url_for('riders_list'))
    u = User.query.get_or_404(int(user_id))
    if Rider.query.filter_by(iduser=u.id).first():
        return redirect(url_for('riders_list'))
    r = Rider(
        iduser=u.id,
        subscription_status='Без абонемента (разовые)',
        subscription_balance=0,
        rental_balance=0,
    )
    db.session.add(r)
    db.session.commit()
    return redirect(url_for('riders_list'))

# --- ОТЧЁТ ПО ВЫРУЧКЕ КЛУБА (HTML + PDF) ---

def _parse_report_dates():
    """Возвращает (start_date, end_date) в формате 'YYYY-MM-DD'.
    По умолчанию — текущий месяц по московскому времени."""
    today = get_msk_now().date()
    default_start = today.replace(day=1)
    default_end = today

    def _safe(value, fallback):
        if not value:
            return fallback
        try:
            return datetime.strptime(value, '%Y-%m-%d').date()
        except ValueError:
            return fallback

    start = _safe(request.args.get('start'), default_start)
    end = _safe(request.args.get('end'), default_end)
    if end < start:
        start, end = end, start
    return start, end


def _query_revenue(start, end):
    """Возвращает агрегированную выручку по услугам за период [start; end]."""
    sql = text("""
        SELECT
            COALESCE(s.type, '')        AS service_type,
            COALESCE(s.name, '—')       AS service_name,
            COALESCE(s.price, 0)        AS price,
            COUNT(w.id)                 AS workouts_count,
            COUNT(w.id) * COALESCE(s.price, 0) AS revenue
        FROM workouts w
        LEFT JOIN services s ON s.id = w.idservice
        WHERE w.status = 'Завершено'
          AND w.datetime_start >= :d_start
          AND w.datetime_start <  :d_end_excl
        GROUP BY s.type, s.name, s.price
        ORDER BY revenue DESC, service_name ASC
    """)
    rows = db.session.execute(sql, {
        'd_start': datetime.combine(start, datetime.min.time()),
        'd_end_excl': datetime.combine(end + timedelta(days=1), datetime.min.time()),
    }).fetchall()

    rows_dicts = [{
        'service_type': r.service_type,
        'service_name': r.service_name,
        'price': float(r.price or 0),
        'workouts_count': int(r.workouts_count or 0),
        'revenue': float(r.revenue or 0),
    } for r in rows]
    total_workouts = sum(r['workouts_count'] for r in rows_dicts)
    total_revenue = sum(r['revenue'] for r in rows_dicts)
    avg_check = (total_revenue / total_workouts) if total_workouts else 0
    return rows_dicts, total_workouts, total_revenue, avg_check


@app.route('/reports/revenue')
@login_required
def revenue_report_view():
    sync_workout_statuses()
    start, end = _parse_report_dates()
    rows, total_workouts, total_revenue, avg_check = _query_revenue(start, end)
    return render_template(
        'revenue.html',
        rows=rows,
        total_workouts=total_workouts,
        total_revenue=total_revenue,
        avg_check=avg_check,
        start_date=start.strftime('%Y-%m-%d'),
        end_date=end.strftime('%Y-%m-%d'),
    )


def _build_revenue_pdf(start, end, rows, total_workouts, total_revenue, avg_check):
    """Формирует PDF-отчёт по выручке клуба."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                    Paragraph, Spacer)

    # Регистрируем кириллический шрифт (DejaVu — есть в большинстве Linux-дистрибутивов).
    font_dir = '/usr/share/fonts/truetype/dejavu'
    candidates = [
        (font_dir + '/DejaVuSans.ttf', font_dir + '/DejaVuSans-Bold.ttf'),
        ('/Library/Fonts/Arial Unicode.ttf', '/Library/Fonts/Arial Unicode.ttf'),
    ]
    font_regular = 'Helvetica'
    font_bold = 'Helvetica-Bold'
    for reg, bold in candidates:
        if os.path.exists(reg) and os.path.exists(bold):
            try:
                pdfmetrics.registerFont(TTFont('AppSans', reg))
                pdfmetrics.registerFont(TTFont('AppSans-Bold', bold))
                font_regular = 'AppSans'
                font_bold = 'AppSans-Bold'
                break
            except Exception as e:
                print(f"DEBUG: PDF font register failed: {e}")

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=20 * mm, rightMargin=15 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
        title='Отчёт по выручке клуба «Гардарика»',
        author='ИС Gardarika',
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'Title', parent=styles['Title'],
        fontName=font_bold, fontSize=18, alignment=1,
        textColor=colors.HexColor('#1B3022'), spaceAfter=6,
    )
    subtitle_style = ParagraphStyle(
        'Subtitle', parent=styles['Normal'],
        fontName=font_regular, fontSize=11, alignment=1,
        textColor=colors.HexColor('#7A7A7A'), spaceAfter=4,
    )
    h2_style = ParagraphStyle(
        'H2', parent=styles['Heading2'],
        fontName=font_bold, fontSize=13,
        textColor=colors.HexColor('#1B3022'), spaceBefore=12, spaceAfter=8,
    )
    body_style = ParagraphStyle(
        'Body', parent=styles['Normal'],
        fontName=font_regular, fontSize=10, leading=14,
    )

    def _fmt(v):
        return f"{v:,.0f}".replace(',', ' ')

    story = []
    story.append(Paragraph('Отчёт по выручке клуба «Гардарика»', title_style))
    story.append(Paragraph(
        f"Период: с {start.strftime('%d.%m.%Y')} по {end.strftime('%d.%m.%Y')}",
        subtitle_style))
    story.append(Paragraph(
        f"Сформирован: {get_msk_now().strftime('%d.%m.%Y %H:%M')} (МСК)",
        subtitle_style))
    story.append(Spacer(1, 8 * mm))

    # Краткая сводка.
    summary_data = [
        ['Завершённые тренировки', str(total_workouts)],
        ['Выручка за период, ₽', _fmt(total_revenue)],
        ['Средний чек, ₽', _fmt(avg_check)],
    ]
    summary_tbl = Table(summary_data, colWidths=[110 * mm, 60 * mm])
    summary_tbl.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), font_regular),
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#7A7A7A')),
        ('TEXTCOLOR', (1, 0), (1, -1), colors.HexColor('#1B3022')),
        ('FONTNAME', (1, 0), (1, -1), font_bold),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('LINEBELOW', (0, 0), (-1, -2), 0.4, colors.HexColor('#E8E5DF')),
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#FBF9F7')),
        ('BOX', (0, 0), (-1, -1), 0.4, colors.HexColor('#E8E5DF')),
    ]))
    story.append(summary_tbl)
    story.append(Spacer(1, 6 * mm))

    story.append(Paragraph('Детализация по услугам', h2_style))

    # Таблица с детализацией.
    head = ['Тип услуги', 'Услуга', 'Цена ₽',
            'Кол-во', 'Выручка ₽']
    body = [head]
    for r in rows:
        body.append([
            r['service_type'] or '—',
            r['service_name'],
            _fmt(r['price']),
            str(r['workouts_count']),
            _fmt(r['revenue']),
        ])
    if rows:
        body.append(['ИТОГО', '', '', str(total_workouts), _fmt(total_revenue)])
    else:
        body.append(['—', 'Завершённых тренировок не найдено', '—', '0', '0'])

    detail_tbl = Table(body,
                       colWidths=[35 * mm, 60 * mm, 22 * mm, 25 * mm, 30 * mm],
                       repeatRows=1)
    style_cmds = [
        ('FONTNAME', (0, 0), (-1, -1), font_regular),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('FONTNAME', (0, 0), (-1, 0), font_bold),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1B3022')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (2, 0), (-1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#E8E5DF')),
    ]
    if rows:
        last = len(body) - 1
        style_cmds += [
            ('FONTNAME', (0, last), (-1, last), font_bold),
            ('BACKGROUND', (0, last), (-1, last), colors.HexColor('#FBF9F7')),
            ('TEXTCOLOR', (0, last), (-1, last), colors.HexColor('#1B3022')),
        ]
    detail_tbl.setStyle(TableStyle(style_cmds))
    story.append(detail_tbl)

    story.append(Spacer(1, 10 * mm))
    story.append(Paragraph(
        'Документ сформирован автоматически информационной системой '
        'конноспортивного клуба «Гардарика».',
        ParagraphStyle('foot', parent=body_style,
                       fontSize=9, alignment=1,
                       textColor=colors.HexColor('#7A7A7A')),
    ))

    doc.build(story)
    pdf = buf.getvalue()
    buf.close()
    return pdf


@app.route('/reports/revenue.pdf')
@login_required
def revenue_report_pdf():
    sync_workout_statuses()
    start, end = _parse_report_dates()
    rows, total_workouts, total_revenue, avg_check = _query_revenue(start, end)
    pdf_bytes = _build_revenue_pdf(start, end, rows,
                                   total_workouts, total_revenue, avg_check)
    filename = f"revenue_{start.strftime('%Y%m%d')}_{end.strftime('%Y%m%d')}.pdf"
    return send_file(
        BytesIO(pdf_bytes),
        mimetype='application/pdf',
        as_attachment=True,
        download_name=filename,
    )


def _migrate_user_profile_fields(is_postgres):
    """Однократная миграция: переносит name/lastname/phone из trainers/riders
    в users и удаляет старые колонки. Безопасно перезапускается."""
    try:
        # 1. Добавляем колонки в users (если их ещё нет)
        if is_postgres:
            db.session.execute(text(
                "ALTER TABLE users "
                "ADD COLUMN IF NOT EXISTS name VARCHAR(100), "
                "ADD COLUMN IF NOT EXISTS lastname VARCHAR(100), "
                "ADD COLUMN IF NOT EXISTS phone VARCHAR(50), "
                "ADD COLUMN IF NOT EXISTS is_approved BOOLEAN DEFAULT TRUE NOT NULL;"
            ))
            db.session.commit()
        # На SQLite db.create_all() уже создал нужные колонки.

        # 2. Переносим имена существующих тренеров в users (если нужно)
        if is_postgres:
            trainer_has_name = db.session.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='trainers' AND column_name='name'"
            )).fetchone() is not None

            if trainer_has_name:
                # Для тренеров без iduser создаём «теневой» User
                orphans = db.session.execute(text(
                    "SELECT id, name, lastname, phone FROM trainers WHERE iduser IS NULL"
                )).fetchall()
                trainer_role = Role.query.filter_by(role_name='Trainer').first()
                for row in orphans:
                    base = (row.name or 'trainer').lower()
                    base = ''.join(ch for ch in base if ch.isalnum() or ch == '_') or 'trainer'
                    candidate = base
                    i = 1
                    while db.session.execute(
                        text("SELECT 1 FROM users WHERE username=:u"),
                        {"u": candidate}).fetchone():
                        i += 1
                        candidate = f"{base}{i}"
                    pw = generate_password_hash(str(uuid.uuid4()),
                                                method='pbkdf2:sha256')
                    db.session.execute(text(
                        "INSERT INTO users(username, password, name, lastname, "
                        "phone, first_name, last_name, idrole, is_approved) "
                        "VALUES (:u,:p,:n,:l,:ph,:n,:l,:r,TRUE) RETURNING id"
                    ), {
                        "u": candidate, "p": pw, "n": row.name or '',
                        "l": row.lastname or '', "ph": row.phone or '',
                        "r": trainer_role.id if trainer_role else None,
                    })
                    new_uid = db.session.execute(text(
                        "SELECT id FROM users WHERE username=:u"),
                        {"u": candidate}).scalar()
                    db.session.execute(text(
                        "UPDATE trainers SET iduser=:uid WHERE id=:tid"),
                        {"uid": new_uid, "tid": row.id})

                # Копируем имя/фамилию/телефон у тренеров с iduser
                db.session.execute(text("""
                    UPDATE users u
                    SET name = COALESCE(NULLIF(u.name, ''), t.name),
                        lastname = COALESCE(NULLIF(u.lastname, ''), t.lastname),
                        phone = COALESCE(NULLIF(u.phone, ''), t.phone),
                        first_name = COALESCE(NULLIF(u.first_name, ''), t.name),
                        last_name = COALESCE(NULLIF(u.last_name, ''), t.lastname)
                    FROM trainers t
                    WHERE t.iduser = u.id
                """))
                db.session.execute(text(
                    "ALTER TABLE trainers DROP COLUMN IF EXISTS name, "
                    "DROP COLUMN IF EXISTS lastname, "
                    "DROP COLUMN IF EXISTS phone;"))
                db.session.commit()

            rider_has_name = db.session.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='riders' AND column_name='name'"
            )).fetchone() is not None

            if rider_has_name:
                orphans = db.session.execute(text(
                    "SELECT id, name, lastname, phone FROM riders WHERE iduser IS NULL"
                )).fetchall()
                rider_role = Role.query.filter_by(role_name='Rider').first()
                for row in orphans:
                    base = (row.name or 'rider').lower()
                    base = ''.join(ch for ch in base if ch.isalnum() or ch == '_') or 'rider'
                    candidate = base
                    i = 1
                    while db.session.execute(
                        text("SELECT 1 FROM users WHERE username=:u"),
                        {"u": candidate}).fetchone():
                        i += 1
                        candidate = f"{base}{i}"
                    pw = generate_password_hash(str(uuid.uuid4()),
                                                method='pbkdf2:sha256')
                    db.session.execute(text(
                        "INSERT INTO users(username, password, name, lastname, "
                        "phone, first_name, last_name, idrole, is_approved) "
                        "VALUES (:u,:p,:n,:l,:ph,:n,:l,:r,TRUE) RETURNING id"
                    ), {
                        "u": candidate, "p": pw, "n": row.name or '',
                        "l": row.lastname or '', "ph": row.phone or '',
                        "r": rider_role.id if rider_role else None,
                    })
                    new_uid = db.session.execute(text(
                        "SELECT id FROM users WHERE username=:u"),
                        {"u": candidate}).scalar()
                    db.session.execute(text(
                        "UPDATE riders SET iduser=:uid WHERE id=:rid"),
                        {"uid": new_uid, "rid": row.id})

                db.session.execute(text("""
                    UPDATE users u
                    SET name = COALESCE(NULLIF(u.name, ''), r.name),
                        lastname = COALESCE(NULLIF(u.lastname, ''), r.lastname),
                        phone = COALESCE(NULLIF(u.phone, ''), r.phone),
                        first_name = COALESCE(NULLIF(u.first_name, ''), r.name),
                        last_name = COALESCE(NULLIF(u.last_name, ''), r.lastname)
                    FROM riders r
                    WHERE r.iduser = u.id
                """))
                db.session.execute(text(
                    "ALTER TABLE riders DROP COLUMN IF EXISTS name, "
                    "DROP COLUMN IF EXISTS lastname, "
                    "DROP COLUMN IF EXISTS phone;"))
                db.session.commit()
        print("Profile field migration completed.")
    except Exception as e:
        print(f"WARN: profile field migration failed (likely already done): {e}")
        db.session.rollback()


def initialize_database():
    with app.app_context():
        # Определяем тип базы данных
        is_postgres = 'postgresql' in app.config['SQLALCHEMY_DATABASE_URI']

        # 1. Создаем таблицы (если их нет)
        db.create_all()

        # 2. Миграция полей name/lastname/phone из trainers/riders в users
        _migrate_user_profile_fields(is_postgres)

        # 3. Сид ролей
        if not Role.query.first():
            db.session.add_all([
                Role(role_name=n)
                for n in ["SuperAdmin", "Admin", "Trainer", "Rider", "Guest"]])
            db.session.commit()
        else:
            # Дополняем недостающие
            for n in ("SuperAdmin", "Admin", "Trainer", "Rider", "Guest"):
                if not Role.query.filter_by(role_name=n).first():
                    db.session.add(Role(role_name=n))
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

        # 6. Представление для активных абонементов (имена теперь из users)
        try:
            db.session.execute(text("DROP VIEW IF EXISTS v_rider_active_subscriptions CASCADE;"))
            db.session.execute(text("""
                CREATE VIEW v_rider_active_subscriptions AS
                SELECT r.id,
                       COALESCE(u.name, '') AS name,
                       COALESCE(u.lastname, '') AS lastname,
                       r.subscription_balance,
                       r.rental_balance,
                       r.subscription_status
                FROM riders r
                LEFT JOIN users u ON u.id = r.iduser
                WHERE COALESCE(r.subscription_balance, 0) > 0
                   OR COALESCE(r.rental_balance, 0) > 0;
            """))
            db.session.commit()
        except Exception as e:
            print(f"Failed to create view v_rider_active_subscriptions: {e}")

        # 7. Представление v_full_schedule (имена тоже из users)
        if is_postgres:
            try:
                db.session.execute(text("DROP VIEW IF EXISTS v_full_schedule CASCADE;"))
                db.session.execute(text("""
                    CREATE VIEW v_full_schedule AS
                    SELECT
                        w.id AS workout_id,
                        w.datetime_start AS "Дата и время",
                        COALESCE(
                            ur.lastname || ' ' || ur.name,
                            wp.guest_name,
                            'Не назначен'
                        ) AS "Всадник",
                        COALESCE(ut.lastname || ' ' || ut.name, 'Без тренера') AS "Тренер",
                        COALESCE(h.name, 'Не выбрана') AS "Лошадь",
                        COALESCE(s.name, 'Не указана') AS "Услуга",
                        w.status AS "Статус"
                    FROM workouts w
                    LEFT JOIN workout_participants wp ON wp.idworkout = w.id
                    LEFT JOIN riders r ON wp.idrider = r.id
                    LEFT JOIN users ur ON ur.id = r.iduser
                    LEFT JOIN trainers t ON w.idtrainer = t.id
                    LEFT JOIN users ut ON ut.id = t.iduser
                    LEFT JOIN horses h ON wp.idhorse = h.id
                    LEFT JOIN services s ON w.idservice = s.id
                    ORDER BY w.datetime_start;
                """))
                db.session.commit()
            except Exception as e:
                print(f"Failed to create view v_full_schedule: {e}")
                db.session.rollback()

# Инициализация при запуске (только для главного процесса или прямого запуска)
if os.environ.get('GUNICORN_MAIN') == '1' or __name__ == '__main__':
    initialize_database()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
