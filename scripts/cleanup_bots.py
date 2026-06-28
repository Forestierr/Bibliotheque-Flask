import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from project import create_app, db
from project.models import User

def cleanup_bot_accounts():
    app = create_app()
    with app.app_context():
        # Trouver tous les utilisateurs
        users = User.query.all()
        deleted_count = 0
        
        for user in users:
            # Vérifier si l'utilisateur n'a aucun livre ET aucun élève
            # S'il n'a ni livre ni élève, il n'a logiquement pas de prêts
            if len(user.books) == 0 and len(user.students) == 0:
                print(f"Suppression du compte inactif / bot : {user.email} (ID: {user.id})")
                db.session.delete(user)
                deleted_count += 1
                
        db.session.commit()
        print(f"✅ Terminé ! {deleted_count} faux compte(s) supprimé(s).")

if __name__ == "__main__":
    confirm = input("Êtes-vous sûr de vouloir supprimer tous les utilisateurs n'ayant aucun livre ni élève ? (O/N) : ")
    if confirm.lower() == 'o':
        cleanup_bot_accounts()
    else:
        print("Annulation.")
