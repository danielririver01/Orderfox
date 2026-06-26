import time
import sys
from app import create_app

app = create_app()

if __name__ == '__main__':
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        sys.exit(0)
