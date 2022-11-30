import os
import werkzeug.contrib.sessions
import time

import odoo
from odoo import http
from odoo.tools.func import lazy_property


def session_gc(session_store):

    two_hours = time.time() - 7200
    for fname in os.listdir(session_store.path):
        path = os.path.join(session_store.path, fname)
        try:
            if os.path.getmtime(path) < two_hours:
                os.unlink(path)
        except OSError:
            pass
        
                        
http.session_gc = session_gc
