# PostgreSQL Database Setup Guide

## Step 1: Install PostgreSQL

### On Windows:
1. Download from: https://www.postgresql.org/download/windows/
2. Run the installer
3. **Remember the password** you set for the `postgres` user
4. Keep the default port: `5432`

### After Installation - Add to PATH (if needed):
- Add PostgreSQL bin folder to your Windows PATH (usually `C:\Program Files\PostgreSQL\15\bin`)

---

## Step 2: Open PostgreSQL Command Line

### Option A: Using pgAdmin (GUI - Easier)
1. Open **pgAdmin** (installed with PostgreSQL)
2. Right-click on **Databases** → Create → Database
3. Enter name: `certverify_db`
4. Click Save

### Option B: Using Command Line (Advanced)
1. Open **Command Prompt** or **PowerShell**
2. Run: `psql -U postgres`
3. Enter the password you set during installation
4. Run these commands:
   ```sql
   CREATE DATABASE certverify_db;
   \q
   ```

---

## Step 3: Update Database Credentials (if needed)

Edit your `app.py` file, line 34:

```python
SQLALCHEMY_DATABASE_URI = "postgresql://postgres:YOUR_PASSWORD@localhost:5432/certverify_db"
```

Replace:
- `postgres` = PostgreSQL username (default is `postgres`)
- `YOUR_PASSWORD` = The password you set during PostgreSQL installation
- `localhost:5432` = Your PostgreSQL server address and port

**Example:**
```python
SQLALCHEMY_DATABASE_URI = "postgresql://postgres:mypassword123@localhost:5432/certverify_db"
```

---

## Step 4: Install Python Dependencies

Open PowerShell in your project folder and run:

```powershell
pip install -r requirements.txt
```

This installs:
- flask
- flask-sqlalchemy
- flask-login
- psycopg2-binary (PostgreSQL driver)
- All other dependencies

---

## Step 5: Initialize Database Tables

Run the initialization script:

```powershell
python init_db.py
```

You should see:
```
🔧 Creating database tables...
✅ Database tables created successfully!

Tables created:
  - users
  - activity_types
  - student_activities
```

---

## Step 6: Verify Connection

Test the connection by running your app:

```powershell
python app.py
```

You should see:
```
 * Running on http://127.0.0.1:5000
```

Visit `http://localhost:5000` in your browser.

---

## Troubleshooting

### Error: "password authentication failed"
- Check your password in `SQLALCHEMY_DATABASE_URI`
- Verify PostgreSQL is running

### Error: "could not connect to server"
- Ensure PostgreSQL service is running
- Check if port 5432 is correct

### Error: "database 'certverify_db' does not exist"
- Run Step 2 again to create the database

### Error: "psycopg2 not installed"
```powershell
pip install psycopg2-binary
```

---

## Quick Checklist

- [ ] PostgreSQL installed and running
- [ ] Database `certverify_db` created
- [ ] Password updated in `app.py`
- [ ] Python dependencies installed (`pip install -r requirements.txt`)
- [ ] Database tables initialized (`python init_db.py`)
- [ ] App runs successfully (`python app.py`)

