# Database utilities for the AI calling system
# This file can be removed after fixing database issues

def cleanup_database_connections():
    """Clean up any hanging database connections"""
    try:
        from app import db
        db.session.remove()
        db.engine.dispose()
    except Exception as e:
        print(f"Error cleaning up database: {e}")

if __name__ == "__main__":
    cleanup_database_connections()