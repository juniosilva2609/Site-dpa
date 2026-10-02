# -*- coding: utf-8 -*-
"""Atalhos:  python run.py            -> servidor de desenvolvimento (com agendador)
             python run.py agendador  -> só o agendador (sem telas)
             python run.py ciclo      -> executa UM ciclo (para usar com cron) e sai"""

import sys
import time

from app import create_app, db, scheduler

if __name__ == "__main__":
    modo = sys.argv[1] if len(sys.argv) > 1 else "web"
    if modo == "web":
        create_app().run(host="127.0.0.1", port=8000, debug=False)
    else:
        app = create_app(iniciar_agendador=False)
        con = db.conectar(app.config["DB_PATH"])
        if modo == "ciclo":
            print(scheduler.tick(con, forcar_manutencao=True))
        elif modo == "agendador":
            while True:
                scheduler.tick(con)
                time.sleep(scheduler.INTERVALO_SEGUNDOS)
        else:
            sys.exit(__doc__)
