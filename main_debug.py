import ok
from src.config import config
from src.patches.startup import install_startup_patches

if __name__ == '__main__':
    install_startup_patches()
    config = config
    config['debug'] = True
    ok = ok.OK(config)
    ok.start()
