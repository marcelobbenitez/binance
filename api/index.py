"""Entry point de Vercel: expone la app Flask de app.py como función serverless.

Vercel arma el bundle de esta función junto con los módulos del repo, por eso
alcanza con agregar la raíz del proyecto al sys.path e importar `app` tal
cual se usa en local con `python app.py`.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import app  # noqa: E402
