import logging

#Save messages to a log file to print them later, instead of printing them directly
def setup_logger():
    
    # Create a logger with a specific name and set its level to INFO ('normal' info messages)
    logger = logging.getLogger("server_logger")
    logger.setLevel(logging.INFO)

    if logger.handlers:
        return logger

    # Format for log messages
    formatter = logging.Formatter(
        "[%(threadName)s] %(levelname)s: %(message)s"
    )

    # Create a console handler to output log messages to the console
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    # Create a file handler to save log messages to a file named 'server.log'
    file_handler = logging.FileHandler("server.log", encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger