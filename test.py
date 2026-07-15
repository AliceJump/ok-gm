import psutil

for proc in psutil.process_iter(["pid", "name"]):
    if proc.info["name"] and proc.info["name"].lower() == "gakumas.exe":
        try:
            parent = proc.parent()
            print(
                proc.pid,
                "parent=",
                parent.pid if parent else None,
                parent.name() if parent else None
            )
        except Exception:
            pass