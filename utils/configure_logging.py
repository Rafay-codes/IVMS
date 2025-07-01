import os
import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

# ---- Configure logging based on yaml settings file
def configure_logging(log_level:str, src:str = 'ivms'):
     
    # remove any existing handlers
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)

    # see https://stackoverflow.com/questions/9856683/using-pythons-os-path-how-do-i-go-up-one-directory
    log_base_dir = Path(__file__).parents[1] 
    if src == 'ivms':
        log_fname = 'detect_ivms.log'

    log_fullpath_name = f'{log_base_dir}/logs/{log_fname}'            

    logger = logging.getLogger()
    rotating_file_handler = TimedRotatingFileHandler(filename=log_fullpath_name, when='H', interval=6, backupCount=4)    
            
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    rotating_file_handler.setFormatter(formatter)

    logger.addHandler(rotating_file_handler)
    logger.setLevel(log_level)

