"""Create a private local .env from the placeholder template; never overwrite it."""
import os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


def main():
    target=ROOT/'.env'
    try:
        fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    except FileExistsError:
        print('.env already exists; left unchanged.')
        return 0
    with os.fdopen(fd,'w') as f:
        f.write((ROOT/'.env.example').read_text())
    print('Private .env created. Add your key locally when ready; never commit this file. Restart the app after changing it.')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
