import sqlite3
import json
import hashlib
from flask import Flask, render_template, request, redirect, url_for, session, g

app = Flask(__name__)
app.secret_key = 'wayfarer-secret-key-change-in-production'

DATABASE = 'data/users.db'
SPOTS_FILE = 'data/spots.json'
STORIES_FILE = 'data/stories.json'


def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db


@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()


def init_db():
    """Initialize the SQLite database with users table."""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            checklist TEXT DEFAULT '[]'
        )
    ''')
    conn.commit()
    conn.close()


def load_spots():
    """Load spots from JSON file."""
    with open(SPOTS_FILE, 'r') as f:
        return json.load(f)


def load_stories():
    """Load stories from JSON file."""
    with open(STORIES_FILE, 'r') as f:
        return json.load(f)


def get_featured_spot():
    """Get a random featured spot for homepage."""
    spots = load_spots()
    import random
    return random.choice(spots)


def hash_password(password):
    """Hash a password using SHA-256."""
    return hashlib.sha256(password.encode()).hexdigest()


def get_user_from_session():
    """Get user from session if logged in."""
    if 'user_id' in session:
        db = get_db()
        cursor = db.cursor()
        cursor.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],))
        return cursor.fetchone()
    return None


def get_checklist(user):
    """Get user's checklist of visited spots."""
    if user:
        return json.loads(user['checklist'])
    return []


def update_checklist(user_id, spot_id, add=True):
    """Update user's checklist."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT checklist FROM users WHERE id = ?', (user_id,))
    current = json.loads(cursor.fetchone()[0])
    
    if add:
        if spot_id not in current:
            current.append(spot_id)
    else:
        if spot_id in current:
            current.remove(spot_id)
    
    cursor.execute('UPDATE users SET checklist = ? WHERE id = ?', 
                   (json.dumps(current), user_id))
    db.commit()


# Map route corridors to search vibes
CORRIDOR_MAP = {
    'scenic': ['coastal_arc', 'inland_thread'],
    'historic': ['inland_thread', 'river_road'],
    'food': ['coastal_arc', 'river_road'],
    'nature': ['coastal_arc', 'river_road', 'inland_thread']
}


@app.route('/', methods=['GET'])
def home():
    """Homepage with hero and featured spot."""
    featured = get_featured_spot()
    return render_template('home.html', featured=featured)


@app.route('/discover', methods=['GET', 'POST'])
def discover():
    """Discover page showing en-route spots."""
    spots = load_spots()
    from_city = request.form.get('from') or request.args.get('from', '')
    to_city = request.form.get('to') or request.args.get('to', '')
    vibe = request.form.get('vibe') or request.args.get('filter', 'all')
    
    # Determine corridor based on vibe
    if vibe == 'all':
        filtered_spots = spots
    else:
        corridors = CORRIDOR_MAP.get(vibe, [])
        filtered_spots = [s for s in spots if s['corridor'] in corridors]
    
    # Additional category filter
    if vibe != 'all' and vibe in ['scenic', 'historic', 'food', 'nature']:
        filtered_spots = [s for s in filtered_spots if s['category'] == vibe or vibe == 'all']
    
    # Alternate card sizes for staggered layout
    for i, spot in enumerate(filtered_spots):
        if i % 6 == 0:
            spot['card_class'] = 'card--large'
        elif i % 6 == 1:
            spot['card_class'] = 'card--small'
        elif i % 6 == 2:
            spot['card_class'] = 'card--wide'
        elif i % 6 == 3:
            spot['card_class'] = 'card--small'
        elif i % 6 == 4:
            spot['card_class'] = 'card--large'
        else:
            spot['card_class'] = 'card--wide'
    
    return render_template('discover.html', 
                         spots=filtered_spots, 
                         from_city=from_city, 
                         to_city=to_city,
                         current_filter=vibe)


@app.route('/stories', methods=['GET'])
def stories():
    """Stories page with travel essays."""
    story_list = load_stories()
    return render_template('stories.html', stories=story_list)


@app.route('/journey', methods=['GET', 'POST'])
def journey():
    """Journey page with account management and checklist."""
    success = request.args.get('success', None)
    user = get_user_from_session()
    all_spots = load_spots()
    checklist = get_checklist(user) if user else []
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action in ('signup', 'login'):
            email = request.form.get('email', '').strip().lower()
            password = request.form.get('password', '')
            
            db = get_db()
            cursor = db.cursor()
            
            if action == 'signup':
                # Check if user exists
                cursor.execute('SELECT id FROM users WHERE email = ?', (email,))
                if cursor.fetchone():
                    return redirect(url_for('journey', error='email_exists'))
                
                # Create new user
                password_hash = hash_password(password)
                cursor.execute('INSERT INTO users (email, password_hash) VALUES (?, ?)',
                             (email, password_hash))
                db.commit()
                session['user_id'] = cursor.lastrowid
                
            elif action == 'login':
                password_hash = hash_password(password)
                cursor.execute('SELECT id FROM users WHERE email = ? AND password_hash = ?',
                             (email, password_hash))
                result = cursor.fetchone()
                if result:
                    session['user_id'] = result[0]
                else:
                    return redirect(url_for('journey', error='invalid_login'))
        
        elif action == 'logout':
            session.pop('user_id', None)
        
        elif action == 'check_spot':
            spot_id = request.form.get('spot_id')
            if user and spot_id:
                # Toggle spot in checklist
                if spot_id in checklist:
                    update_checklist(user['id'], spot_id, add=False)
                else:
                    update_checklist(user['id'], spot_id, add=True)
        
        return redirect(url_for('journey', success=1))
    
    return render_template('journey.html', 
                         user=user, 
                         checklist=checklist, 
                         all_spots=all_spots,
                         success=success)


if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)
