import sys

if '--classic' in sys.argv[1:]:   # the tabbed window (gui/app.py) the launcher replaced; the launcher's gear menu opens it too
    from gui.app import main
    sys.exit(main([a for a in sys.argv if a != '--classic']))
from gui.launcher import main

sys.exit(main(sys.argv))
