# Certificate Verification System (B.Tech Major Project)

A secure, digital platform for issuing, verifying, and managing student activity certificates. Built with Flask, PostgreSQL, and hashing for integrity.

## Features
- **Student Dashboard**: Submit activity certificates, view status, generate portfolio PDF.
- **Faculty/Admin Dashboard**: Review pending requests, approve/reject with comments.
- **Auto-Verification**: Automated checks for URL reachability and name matching.
- **Public Verification**: QR/Link-based verification for third parties.
- **Secure Hash Storage**: Tamper-proof certificate tracking using SHA-256.

## Setup Instructions

### 1. Database Setup (PostgreSQL)
1. Install PostgreSQL and create a database named `smarthub` (or update `config.py` with your DB name).
2. Update `config.py` with your PostgreSQL credentials:
   ```python
   SQLALCHEMY_DATABASE_URI = "postgresql://postgres:YOUR_PASSWORD@localhost:5432/smarthub"
   ```

### 2. Installation
1. Install Python 3.10+.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

### 3. Initialize Database
Run the initialization script to create tables and default users:
```bash
python scripts/init_db.py
```
*Note: This will reset the database and create a default admin user.*

### 4. Run the Application
```bash
python run.py
```
Access the app at `http://localhost:5000`.

## Default Credentials
- **Admin**: `admin@example.com` / `admin123`
- **Faculty (Dr. Smith)**: `drsmith@college.edu` / `password`
- **HOD CSE**: `hod.cse@college.edu` / `password`

## Project Structure
- `app/`: Core application (Routes, Models, Templates, Static).
- `scripts/`: Utility scripts.
- `docs/`: Design and Architecture documentation.
- `config.py`: Configuration settings.
- `run.py`: Application entry point.
