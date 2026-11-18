"""Trusted local-operator recovery. Not exposed through the web application.

Stop the application first. Requires write access to the workspace database.
Password is prompted, never accepted in process arguments. Revokes all sessions.
"""
import argparse
import getpass
import os
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from threadgate.config import load_environment
from threadgate.workspace import Workspace,password_hash


def main():
    load_environment(ROOT)
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--username',required=True)
    parser.add_argument('--reset-mfa',action='store_true')
    args=parser.parse_args()
    path=Path(os.getenv('THREADGATE_WORKSPACE_DB',str(ROOT/'data/runs/workspace.sqlite3')))
    if not path.is_file():
        raise SystemExit('Workspace database does not exist.')
    if input('Type the username again to confirm local recovery: ')!=args.username:
        raise SystemExit('Confirmation did not match.')
    password=getpass.getpass('New password (14+ characters): ')
    if password!=getpass.getpass('Confirm new password: '):
        raise SystemExit('Passwords did not match.')
    encoded=password_hash(password)
    service=Workspace(path)
    with service._db(write=True) as db:
        if not db.execute('SELECT 1 FROM users WHERE username=?',(args.username,)).fetchone():
            raise SystemExit('Account not found.')
        db.execute('UPDATE users SET password_hash=?,active=1 WHERE username=?',(encoded,args.username))
        db.execute('DELETE FROM sessions WHERE username=?',(args.username,))
        db.execute('DELETE FROM login_failures WHERE username=?',(args.username,))
        if args.reset_mfa:
            db.execute('DELETE FROM user_mfa WHERE username=?',(args.username,))
        service._audit(db,'local-operator','ACCOUNT_RECOVERED',username=args.username,mfa_reset=args.reset_mfa)
    print('Account recovered. Sessions revoked. Restart the app and sign in; re-enrol MFA if reset.')


if __name__=='__main__':
    main()
