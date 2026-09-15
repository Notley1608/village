from .config import load_config, residents


def daily_dispatch(config_path: str = None) -> None:
    cfg = load_config(config_path) if config_path else load_config()
    for resident in residents(cfg):
        pass


def run() -> None:
    daily_dispatch()


if __name__ == "__main__":
    run()