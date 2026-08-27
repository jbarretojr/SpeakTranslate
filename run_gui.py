import os
import sys

SRC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src', 'speaktranslate')
sys.path.insert(0, SRC_DIR)

from gui import main

if __name__ == '__main__':
    main()
