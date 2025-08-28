import logging
from logging.handlers import RotatingFileHandler


def get_logger(log_path: str) -> logging.Logger:
	logger = logging.getLogger("lidar_web_pipeline")
	logger.setLevel(logging.INFO)
	logger.propagate = False

	# Avoid duplicate handlers
	if logger.handlers:
		return logger

	formatter = logging.Formatter(
		fmt="%(asctime)s | %(levelname)s | %(message)s",
		datefmt="%Y-%m-%d %H:%M:%S",
	)

	file_handler = RotatingFileHandler(log_path, maxBytes=5 * 1024 * 1024, backupCount=3)
	file_handler.setLevel(logging.INFO)
	file_handler.setFormatter(formatter)
	logger.addHandler(file_handler)

	stream_handler = logging.StreamHandler()
	stream_handler.setLevel(logging.INFO)
	stream_handler.setFormatter(formatter)
	logger.addHandler(stream_handler)

	return logger