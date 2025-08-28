import os
from dataclasses import dataclass


def ensure_dir(path: str) -> str:
	os.makedirs(path, exist_ok=True)
	return path


@dataclass
class OutputPaths:
	base: str
	textures: str
	panos: str
	logs: str
	intermediates: str

	def __init__(self, base: str) -> None:
		self.base = os.path.abspath(base)
		self.textures = os.path.join(self.base, "textures")
		self.panos = os.path.join(self.base, "panos")
		self.logs = os.path.join(self.base, "logs")
		self.intermediates = os.path.join(self.base, "intermediates")

		for d in [self.base, self.textures, self.panos, self.logs]:
			ensure_dir(d)