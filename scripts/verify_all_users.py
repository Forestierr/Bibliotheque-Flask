import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from project import create_app, db
from project.models import User

def verify_all_existing_users():
    app = create_app()
    with app.app_context():
        users = User.query.all()
        updated_count = 0
        for user in users:
            if not user.is_verified:
                user.is_verified = True
                updated_count += 1
        db.session.commit()
        print(f"{updated_count} utilisateur(s) mis à jour en 'is_verified = True'.")

if __name__ == "__main__":
    verify_all_existing_users()
